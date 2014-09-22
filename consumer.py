# Refactored consumer for VTechWorks

import requests
from datetime import date, timedelta
import time
from lxml import etree 
from scrapi_tools import lint
from scrapi_tools.document import RawDocument, NormalizedDocument

NAME = 'vtechworks'
TODAY = date.today()
NAMESPACES = {'dc': 'http://purl.org/dc/elements/1.1/', 
            'oai_dc': 'http://www.openarchives.org/OAI/2.0/',
            'ns0': 'http://www.openarchives.org/OAI/2.0/'}

def consume(days_back=5):

    start_date = str(date.today() - timedelta(days_back))
    base_url = 'http://vtechworks.lib.vt.edu/oai/request?verb=ListRecords&metadataPrefix=oai_dc&from='
    start_date = TODAY - timedelta(days_back)
    # YYYY-MM-DD hh:mm:ss
    url = base_url + str(start_date) + ' 00:00:00'

    records = get_records(url)

    xml_list = []
    for record in records:
        doc_id = record.xpath('ns0:header/ns0:identifier', namespaces=NAMESPACES)[0].text
        record = etree.tostring(record)
        record = '<?xml version="1.0" encoding="UTF-8"?>\n' + record
        xml_list.append(RawDocument({
                    'doc': record,
                    'source': NAME,
                    'doc_id': doc_id,
                    'filetype': 'xml'
                }))

    return xml_list

def get_records(url):
    data = requests.get(url)
    doc = etree.XML(data.content)
    records = doc.xpath('//ns0:record', namespaces=NAMESPACES)
    token = doc.xpath('//ns0:resumptionToken/node()', namespaces=NAMESPACES)

    if len(token) == 1:
        time.sleep(0.5)
        base_url = 'http://vtechworks.lib.vt.edu/oai/request?verb=ListRecords&resumptionToken=' 
        url = base_url + token[0]
        records += get_records(url)

    return records


def getcontributors(result):
    contributors = result.xpath('//dc:contributor/node()', namespaces=NAMESPACES) or ['']
    creators = result.xpath('//dc:creator/node()', namespaces=NAMESPACES) or ['']
    all_contributors = contributors + creators
    contributor_list = []
    for person in all_contributors:
        contributor_list.append({'full_name': person, 'email': ''})

    # TODO: this currently deals with non-person contributors by just removing the first name 
    if len(contributor_list) > 1:
        contributor_list.pop(0)

    return contributor_list

def gettags(result):
    tags = result.xpath('//dc:subject/node()', namespaces=NAMESPACES) or []
    return tags

def getabstract(result):
    abstract = result.xpath('//dc:description/node()', namespaces=NAMESPACES) or ['No abstract']
    return abstract[0]

def getids(result):
    service_id = result.xpath('ns0:header/ns0:identifier/node()', namespaces=NAMESPACES)[0]
    identifiers = result.xpath('//dc:identifier/node()', namespaces=NAMESPACES)
    url = ''
    doi = ''
    for item in identifiers:
        if 'hdl.handle.net' in item:
            url = item
        if 'dx.doi.org' in item:
            doi = item

    if url == '':
        raise Exception('Warning: No url provided!')

    return {'service_id': service_id, 'url': url, 'doi': doi}

def get_earliest_date(result):
    dates = result.xpath('//dc:date/node()', namespaces=NAMESPACES)
    date_list = []
    for item in dates:
        try:
            a_date = time.strptime(str(item)[:10], '%Y-%m-%d')
        except ValueError:
            try:
                a_date = time.strptime(str(item)[:10], '%Y')
            except ValueError:
                try:
                    a_date = time.strptime(str(item)[:10], '%m/%d/%Y')
                except ValueError:
                    try:
                        a_date = time.strptime(str(item)[:10], '%Y-%d-%m')
                    except ValueError:
                        a_date = time.strptime(str(item)[:10], '%Y-%m')
        date_list.append(a_date)
    min_date =  min(date_list) 
    min_date = time.strftime('%Y-%m-%d', min_date)

    return min_date

def normalize(raw_doc, timestamp):
    result = raw_doc.get('doc')
    try:
        result = etree.XML(result)
    except etree.XMLSyntaxError:
        print "Error in namespaces! Skipping this one..."
        return None

    title = result.xpath('//dc:title/node()', namespaces=NAMESPACES)[0]
    result_type = result.xpath('//dc:type/node()', namespaces=NAMESPACES)
    rights = result.xpath('//dc:rights/node()', namespaces=NAMESPACES) or ['']
    identifiers = result.xpath('//dc:identifier/node()', namespaces=NAMESPACES) or ['']
    publisher = (result.xpath('//dc:publisher/node()', namespaces=NAMESPACES) or [''])[0]

    payload = {
        'title': title,
        'contributors': getcontributors(result),
        'properties': {
            'type': result_type,
            'rights': rights[0],
            'identifiers': identifiers,
            'publisher': publisher
        },
        'description': getabstract(result),
        'tags': gettags(result),
        'meta': {},
        'id': getids(result),
        'source': NAME,
        'date_created': get_earliest_date(result),
        'timestamp': str(timestamp)
    }

    return NormalizedDocument(payload)

if __name__ == '__main__':
    print(lint(consume, normalize))
