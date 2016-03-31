import os
import redis
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.wsgi import SharedDataMiddleware
from werkzeug.utils import redirect
from jinja2 import Environment, FileSystemLoader

class Shortly(object):
    '''The magnificent example - Shortly app'''
    def __init__(self, config):
        '''Constructs a Shortly instance'''
        # starting connection to a redis-server
        self.redis = redis.Redis(config['redis_host'],
                                 config['redis_port'])
        # sets the template path to a 'templates' directory where this file
        # resides
        template_path = os.path.join(os.path.dirname(__file__), 'templates')
        #creating jinja environment
        self.jinja_env = Environment(loader=FileSystemLoader(template_path),
                                     autoescape=True)
        # mapping of addresses and functions to be invoked
        self.url_map = Map([Rule('/', endpoint='new_url'),
                            Rule('/<short_id>', endpoint='follow_short_link'),
                            Rule('/<short_id>+', endpoint='short_link_details')])

    def dispatch_request(self, request):
        '''Dispatches a received request towards its recipient'''
        #return Response('Hello, World!')
        #creating an adapter object with the url mapping
        # TODO: check the adapter method in case any non existing url is provided
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            # getting the endpoint for an url and the values (if any)
            endpoint, values = adapter.match()
            # invoking the hander method for the received request
            return getattr(self, 'on_' + endpoint)(request, **values)
        except HTTPException as e:
            return 'exception!', e

    def wsgi_app(self, environ, start_response):
        ''' '''
        request = Request(environ)
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        ''' '''
        return self.wsgi_app(environ, start_response)

    def render_template(self, template_name, **context):
        ''' '''
        t = self.jinja_env.get_template(template_name)
        return Response(t.render(context), mimetype='text/html')

    def on_new_url(self, request):
        ''' '''
        error = None
        url = ''
        if request.method == 'POST':
            url = request.form['url']
            if not is_valid_url(url):
                error = 'Please enter a valid URL'
            else:
                short_id = self.insert_url(url)
                return redirect('/{}+'.format(short_id))
        return self.render_template('new_url.html', error=error, url=url)

    def insert_url(self, url):
        ''' '''
        short_id  = self.redis.get('revers-url:' + url)
        if short_id is not None:
            return short_id
        url_num = self.redis.incr('last-url-id')
        short_id = base36_encode(url_num)
        self.redis.set('url-target:' + short_id, url)
        self.redis.set('reverse-url:' + url, short_id)
        return short_id

    def on_short_link_details(self, request, short_id):
        ''' '''
        link_target = self.redis.get('url-target:' + short_id)
        if link_target is None:
            raise NotFound
        click_count = int(self.redis.get('click-count:' + short_id) or 0)
        return self.render_template('short_link_details.html',
                                     link_target=link_target,
                                     short_id=short_id,
                                     click_count=click_count)

    def on_follow_short_link(self, request, short_id):
        ''' '''
        link_target = self.redis.get('url-target:' + short_id)
        if link_target is None:
            return NotFound
        self.redis.incr('click-count:' + short_id)
        return redirect(link_target)


def base36_encode(number):
    '''Basic encoding used for providing unque keys in redis'''
    assert number >= 0
    if number == 0:
        return '0'
    base36 = []
    while number != 0:
        number, i = divmod(number, 36)
        base36.append('0123456789abcdefghijklmnopqrstuvwxyz'[i])
    return ''.join(reversed(base36))

def is_valid_url(url):
    '''Checks a given link for validity'''
    # splitting an url to components
    parts = urlparse(url)
    # checks if a given link contains http or https and that is the condition
    # for validity..
    return parts.scheme in ('http', 'https')

def create_app(redis_host='localhost', redis_port=6379, with_static=True):
    '''Factory function for creating Shortly apps'''
    app = Shortly({'redis_host': redis_host,
                   'redis_port': redis_port})
    if with_static:
        app.wsgi_app = SharedDataMiddleware(app.wsgi_app,
            {'/static': os.path.join(os.path.dirname(__file__), 'static')})
    return app

# what should be performed if this module is run as standalone app
if __name__ == '__main__':
    # importing the web server from werkzeug, it is needed only if we run the
    from werkzeug.serving import run_simple
    #creating an app
    app = create_app()
    # running an instance of the application
    run_simple('0.0.0.0', 5000, app, use_debugger=True, use_reloader=True)
