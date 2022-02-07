import json
import logging
import os
import sys
import xml.etree.ElementTree as et

import requests
import furl
from dotenv import load_dotenv
from flask import Flask, Response
from flask_compress import Compress

# Generate and serve a sitemap.xml file for Avalon public interface
# using the the Avalon API

# Add any environment variables from .env
load_dotenv('../.env')

# Get environment variables
env = {}
for key in ('AVALON_PUBLIC_URL', 'AVALON_API_URL', 'AVALON_API_TOKEN'):
    env[key] = os.environ.get(key)
    if env[key] is None:
        raise RuntimeError(f'Must provide environment variable: {key}')

public_url = furl.furl(env['AVALON_PUBLIC_URL'])
api_url = furl.furl(env['AVALON_API_URL'])
token = env['AVALON_API_TOKEN']
debug = os.environ.get('FLASK_ENV') == 'development'


def generate_sitemap():
    """ Generate the sitemap. """

    logger = logging.getLogger('sitemap')

    logger.addHandler(logging.StreamHandler())
    if debug:
        logger.setLevel(logging.DEBUG)

        # from http.client import HTTPConnection
        # HTTPConnection.debuglevel = 1
        # requests_log = logging.getLogger("requests.packages.urllib3")
        # requests_log.setLevel(logging.DEBUG)
        # requests_log.propagate = True
    else:
        logger.setLevel(logging.INFO)

    logger.info("Begin generating sitemap.xml")

    headers = {'Avalon-Api-Key': env['AVALON_API_TOKEN']}
    print(headers)

    # Start the xml output
    NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'

    urlset = et.Element(et.QName(NS, 'urlset'))
    urlset.tail = '\n'

    doc = et.ElementTree(urlset)

    # Add the homepage
    url = et.SubElement(urlset, et.QName(NS, 'url'))
    loc = et.SubElement(url, et.QName(NS, 'loc'))
    loc.text = api_url.url
    url.tail = '\n'

    # Iterate over collections
    collections_url = (api_url / 'admin' / 'collections.json').url
    logger.debug(f'{collections_url=}')

    response = requests.get(collections_url, headers=headers, params={'per_page': '100', 'page': '1'})
    # logger.debug(f'{response=}')

    collections = json.loads(response.text)

    for collection in collections:

        # Determine if this collection has any published objects
        if collection['object_count']['published'] > 0:

            # Add this collection
            collection_id = collection['id']
            collection_name = collection['name']

            logger.debug(f'Adding {collection_id=} {collection_name=}')

            url = et.SubElement(urlset, et.QName(NS, 'url'))
            loc = et.SubElement(url, et.QName(NS, 'loc'))
            loc.text = (public_url / 'collections' / collection_id).url
            url.tail = '\n'

            # Iterate over objects in this collection
            page = 1
            per_page = 100

            objects_url = (api_url / 'admin' / 'collections' / collection_id / 'items.json').url
            logger.debug(f'{objects_url=}')

            # Continue requesting pages until we are returned fewer than per_page
            # number of objects
            while True:

                response = requests.get(objects_url,
                                        headers=headers,
                                        params={'per_page': per_page, 'page': page})

                objects = json.loads(response.text)

                # Iterate over this page of objects
                for object_id, object  in objects.items():

                    # Check if this object is published
                    if object['published']:

                        # Add this object
                        object_title = object['title']
                        logger.debug(f'Adding {object_id=} {object_title=}')

                        url = et.SubElement(urlset, et.QName(NS, 'url'))
                        loc = et.SubElement(url, et.QName(NS, 'loc'))
                        loc.text = (public_url / 'media_objects' / object_id).url
                        url.tail = '\n'

                if len(objects) < per_page:
                    break

                page += 1

    logger.info("sitemap.xml generation complete")

    # Write the XML Sitemap to stdout
    return et.tostring(
            urlset,
            encoding='unicode',
            method='xml',
            xml_declaration=True,
            default_namespace=NS)


# Generate the sitemap once a startup
sitemap = generate_sitemap()

# Start the flask app, with compression enabled
app = Flask(__name__)
Compress(app)


@app.route('/')
def root():
    return {'status': 'ok'}


@app.route('/ping')
def ping():
    return {'status': 'ok'}


@app.route('/sitemap.xml')
def get_sitemap():
    return Response(sitemap, mimetype='text/xml')


if __name__ == '__main__':
    # This code is not reached when running "flask run". However the Docker
    # container runs "python app.py" and host='0.0.0.0' is set to ensure
    # that flask listents to port 5000 on all interfaces.
    app.run(host='0.0.0.0')
