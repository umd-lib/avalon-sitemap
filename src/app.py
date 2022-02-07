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
# using the the Avalon Solr index.

# Add any environment variables from .env
load_dotenv('../.env')

# Get environment variables
env = {}
for key in ('AVALON_PUBLIC_URL', 'AVALON_SOLR_URL'):
    env[key] = os.environ.get(key)
    if env[key] is None:
        raise RuntimeError(f'Must provide environment variable: {key}')

public_url = furl.furl(env['AVALON_PUBLIC_URL'])
solr_url = furl.furl(env['AVALON_SOLR_URL'])
debug = os.environ.get('FLASK_ENV') == 'development'


def generate_sitemap():
    """ Generate the sitemap. """

    logger = logging.getLogger('sitemap')

    logger.addHandler(logging.StreamHandler())
    if debug:
        logger.setLevel(logging.DEBUG)

        from http.client import HTTPConnection
        HTTPConnection.debuglevel = 1
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
    else:
        logger.setLevel(logging.INFO)

    logger.info("Begin generating sitemap.xml")

    # Start the xml output
    NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'

    urlset = et.Element(et.QName(NS, 'urlset'))
    urlset.tail = '\n'

    doc = et.ElementTree(urlset)

    # Add the homepage
    url = et.SubElement(urlset, et.QName(NS, 'url'))
    loc = et.SubElement(url, et.QName(NS, 'loc'))
    loc.text = public_url.url
    url.tail = '\n'

    # Setup the Solr query
    search_url = (solr_url / 'solr' / 'avalon' / 'select').url

    q = ' AND '.join([
        "has_model_ssim:MediaObject", # is a media object
        "avalon_publisher_ssi:*", # object is published
        "hidden_bsi:false", # object is not hidden from search results
    ])

    count = 0 # count of objects have we seen
    rows = 100 # rows to page in single request

    params = {
        'q': q, # query
        'fl': 'id,title_tesi,isMemberOfCollection_ssim', # field list to return for each object
        'sort': 'system_create_dtsi asc', # sort in object creation order
        'wt': 'json', # response format JSON
        'start': count, # return results starting at this row
        'rows': rows, # number of rows to page
    }

    collections = set() # track collections we have seen already

    # Iterate over all response objects
    while True:

        response = requests.get(search_url, params=params)

        data = json.loads(response.text)

        # Iterate over objects in this response
        for object in data['response']['docs']:

            object_id = object['id']
            object_title = object['title_tesi']

            # Iterate over the collection ids
            for collection_id in object['isMemberOfCollection_ssim']:

                if collection_id not in collections:

                    # This is the first time seeing this collection
                    logger.debug(f'Adding {collection_id=}')

                    url = et.SubElement(urlset, et.QName(NS, 'url'))
                    loc = et.SubElement(url, et.QName(NS, 'loc'))
                    loc.text = (public_url / 'collections' / collection_id).url
                    url.tail = '\n'

                    collections.add(collection_id)

            logger.debug(f'Adding {object_id=} {object_title=}')

            url = et.SubElement(urlset, et.QName(NS, 'url'))
            loc = et.SubElement(url, et.QName(NS, 'loc'))
            loc.text = (public_url / 'media_objects' / object_id).url
            url.tail = '\n'

            count += 1

        total = int(data['response']['numFound'])

        if count >= total:
            break

        params['start'] = count

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
