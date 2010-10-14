#!/usr/bin/python
from __future__ import with_statement
from gevent import monkey; monkey.patch_all()
from gevent import wsgi
from gevent import Greenlet
import gevent
from gevent.queue import Queue
import pymongo
from pymongo import objectid
import os
from lxml import etree
import redis
import sys
import urllib2
import simplejson as json
import uuid
import re

# Configuration!!
MONGO_HOST = ''
REDIS_HOST = ''

# See http://goo.gl/NQZX
PCODES_TEMPLATE_IDS = { 'COBSCAT': '1.3.6.1.4.1.19376.1.5.3.1.4.13.2'
                        ,'MEDCCAT': '1.3.6.1.4.1.19376.1.5.3.1.4.5'
                        , 'CONDLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.1'
                        , 'PROBLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.2'
                        , 'INTOLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.3'
                        , 'RISKLIST': '1.3.6.1.4.1.19376.1.5.3.1.4.5.1'
                        , 'LABCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.13'
                        , 'DICAT':'1.3.6.1.4.1.19376.1.5.3.1.4.13'
                        , 'RXCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'MEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'CURMEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'DISCHMEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'HISTMEDLIST':'1.3.6.1.4.1.19376.1.5.3.1.4.7'
                        , 'IMMUCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.12'
                        , 'PSVCCAT':'1.3.6.1.4.1.19376.1.5.3.1.4.14' # XXX
                        }

def parsePid(patientId):
    delim = '^^^&' # see http://is.gd/fNUSv (search for sourcePatientInfo)
    pid = patientId
    pidroot = ''
    i = patientId.find(delim)
    if i>0:
        pid = patientId[:i]
        i += len(delim)
        j = patientId.find('&ISO', i)
        pidroot = patientId[i:j] if j > 0 else patientId[i:]
    return (pid, pidroot)

def create_pcc10(subscription, entries):
    (pid, pidroot) = parsePid(subscription['patientId'])
    patName = subscription['patientName']
    return """<QUPC_IN043200UV01 xmlns='urn:hl7-org:v3' ITSVersion='XML_1.0'
  xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'>
  <id root='1' extension='1'/>
  <creationTime value='201011111111'/>
  <interactionId extension='QUPC_IN043200UV' root='2.16.840.1.113883.5'/>
  <processingCode code='D'/>
  <processingModeCode code='T'/>
  <acceptAckCode code='AL'/>
  <receiver typeCode="RCV">
    <device determinerCode='INSTANCE'>
      <id/>
      <name/>
      <telecom value='1' />
      <manufacturerModelName/>
      <softwareName/>
    </device>
  </receiver>
  <sender typeCode="SND">
    <device determinerCode='INSTANCE'>
      <id/>
      <name/>
      <telecom value='1' />
      <manufacturerModelName/>
      <softwareName/>
    </device>
  </sender>
  <controlActProcess moodCode='EVN'>
    <id extension='1'/>
    <code code='QUPC_TE043200UV'/>
    <effectiveTime value='1'/>
    <authorOrPerformer typeCode='1'></authorOrPerformer>
    <subject>
      <registrationEvent>
	<statusCode code='active'/>
	<custodian>
	  <assignedEntity>
	    <id root='1' extension='1'/>
	    <addr></addr>
	    <telecom></telecom>
	    <assignedOrganization>
	      <name></name>
	    </assignedOrganization>
	  </assignedEntity>
	</custodian>
	<subject2>
	  <careProvisionEvent>
	    <recordTarget>
             <patient>
		<id root='%s' extension='%s'/>
		<addr></addr>
		<telecom value='1' use='1'/>
		<statusCode code='active'/>
                <patientPerson>
                  <name>
                       <given>%s</given>
                       <family>%s</family>
                  </name>
                </patientPerson>
	      </patient>
	    </recordTarget>
            <pertinentInformation3>
%s
            </pertinentInformation3>
          </careProvisionEvent>
	</subject2>
      </registrationEvent>
    </subject>
    <queryAck>
      <queryId extension='%s'/>
      <statusCode code='1'/>
      <queryResponseCode code='1'/>
      <resultCurrentQuantity value='1'/>
      <resultRemainingQuantity value='1'/>
    </queryAck>
  </controlActProcess>
</QUPC_IN043200UV01>""" % (pidroot, 
                           pid, 
                           patName['given'],
                           patName['family'],
                           "\n".join([etree.tostring(x, xml_declaration=False) for x in entries]),
                           subscription['queryId'])

DEFAULT_CARE_MANAGER = 'http://139.91.190.40:8080/axis2/services/QUPC_AR004030UV_Service'
def send_pcc10(subscription, entries):
    endpoint = subscription['endpoint_']
    if endpoint is None:
        endpoint = DEFAULT_CARE_MANAGER
    req = urllib2.Request(endpoint)
    req.add_header('content-type', 'application/soap+xml;charset=utf-8;action="urn:hl7-org:v3:QUPC_IN043200UV01"')
    xml = create_pcc10(subscription, entries)
    soap = """<?xml version='1.0' encoding='UTF-8'?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope">
<soapenv:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">
<wsa:Action soapenv:mustUnderstand='1'>urn:hl7-org:v3:QUPC_IN043200UV01</wsa:Action>
<wsa:MessageID>%s</wsa:MessageID>
</soapenv:Header>
<soapenv:Body>%s</soapenv:Body>
</soapenv:Envelope>""" % (uuid.uuid4().urn, xml)
    req.add_data(soap.encode('utf-8'))
    print 'SENDING\n', soap
    try:
        fp = urllib2.urlopen(req)
        response = fp.read()
        print 'SUBMITTED AND GOT\n',response
    except urllib2.URLError, ex:
        msg = ex.read()
        print "PCC10 Error: %s %s" % (ex.code, msg)
        raise ex
    except:
        print "PCC10 Unexpected error:", sys.exc_info()[0]
        raise

class SubscriptionLet(Greenlet):
    def __init__(self, subscription, timeout = 30):
        gevent.Greenlet.__init__(self)
        self.subscription = subscription
        self.timeout = timeout
        self._q = Queue()
        self.checking = False

    def id(self):
        return self.subscription.get('id')

    def stop():
        self._q.put_nowait({'op':'stop'})
    def wakeup():
        self._q.put_nowait({'op':'wakeup'})
        
    def match_subscription(self, doc):
        provcode = self.subscription.get('careProvisionCode')
        q = "h:component/h:structuredBody/h:component/h:section/h:entry//*"
        if provcode is not None:
            q += "[h:templateId/@root='%s']" % PCODES_TEMPLATE_IDS.get(provcode)
        l = doc.xpath(q, namespaces={'h':'urn:hl7-org:v3'})
        return l

    def check_subscription(self):
        subscription = self.subscription
        id = self.id()
        print '[%s] Now at subscr' % id, self.subscription
        entries = []
        moncon = pymongo.Connection(MONGO_HOST)
        try:
            docsdb = moncon.xds.docs
            lastUpdated = subscription['lastChecked_']
            endpoint = subscription.get('endpoint_') or 'http://example.org/'
            patientId = subscription['patientId']
            patre = re.compile('^' + patientId+'\^')
            query = {'patientId':patre, 'mimeType': 'text/xml', 'storedAt_':{'$gt': lastUpdated}}
            careRecordTimePeriod = subscription.get('careRecordTimePeriod')
            # if careRecordTimePeriod is not None:
            #    query['creationTime'] = {'$gte':careRecordTimePeriod['low'], 
            #                             '$lte':careRecordTimePeriod['high']}
            # clinicalStatementTimePeriod = subscription.get('clinicalStatementTimePeriod')
            # if clinicalStatementTimePeriod is not None:
            #    query['creationTime'] = {'$gte':clinicalStatementTimePeriod['low'], 
            #                             '$lte':clinicalStatementTimePeriod['high']}
            print 'MONQ=', query
            crs = docsdb.find(query, fields=['filename', 'storedAt_'], 
                              sort=[('storedAt_', pymongo.ASCENDING)])
            for d in crs:
                print '-->', d['filename']
                doc = None
                with open('static/'+d['filename'], 'rb') as fp:
                    doc = etree.parse(fp).getroot()
                e = self.match_subscription(doc)
                entries.extend(e)
                subscription['lastChecked_'] = d['storedAt_']
                moncon.xds.pcc.update({'_id':objectid.ObjectId(self.id())},
                                      {"$set": {"lastChecked_": d['storedAt_']}})
        finally:
            moncon.disconnect()
        print '[%s] Found' % (id,),entries
        if len(entries) > 0:
            send_pcc10(self.subscription, entries)
        return entries
    def __str__(self):
        cpc = self.subscription.get('careProvisionCode')
        if cpc is None:
            cpc = ""
        return """Subscription (%s)""" % self.subscription

    def _run(self):
            while True:
                try:
                    self.checking = True
                    self.check_subscription()
                except Exception, e:
                    print 'Oh no! just got: '+str(e)
                    raise
                finally:
                    self.checking = False
                print "[%s] Going to sleep for %d secs ..." % (self.id(), self.timeout)
                try:
                    op = self._q.get(timeout=self.timeout)
                except gevent.queue.Empty:
                    op = {'op':'wakeup'}
                if op['op'] == 'stop':
                    break
                # gevent.sleep(30)
                

workers = {}
from collections import defaultdict
workers_per_patient = defaultdict(list)

def monitor_new_subscriptions(timeout):
    r = redis.Redis(host=REDIS_HOST)
    key = 'xds:pcc-cm:new-subscr'
    while True:
        try:
            (_,s) = r.blpop(key)
            print 'Got New subscription!!', s
            sub = json.loads(s)
            if workers.has_key(sub.get('id')):
                continue
            g = SubscriptionLet(sub, timeout)
            g.start_later( 1 )
            workers[g.id()] = g
            workers_per_patient[sub['patientId']].append(g)
        except:
            pass

def monitor_new_submissions():
    r = redis.Redis(host=REDIS_HOST)
    key = 'xds:pcc-cm:new-submission'
    while True:
        try:
            (_,s) = r.blpop(key)
            sub = json.loads(s)
            patId = sub['patientId']
            print "Got New submission set for patient='%s'" % patId
            if not workers_per_patient.has_key(patId):
                continue
            for g in workers_per_patient[patId]:
                g.wakeup()
        except:
            pass
def schedule_all(timeout):
    """Create the worker threads for the currently available PCC-9 subscriptions"""
    print 'Registering workers per PCC-9 subscription...'
    moncon = pymongo.Connection(MONGO_HOST)
    import random
    random.seed(47)
    try:
        pcc = moncon.xds.pcc
        for i in pcc.find():
            ids = str(i.get('_id'))
            del i['_id']
            i['id'] = ids
            period = timeout + random.randint(-30, 29) 
            g = SubscriptionLet(i, period)
            g.start()
            workers[ids] = g
            workers_per_patient[i['patientId']].append(g)
    except Exception, e:
        print 'Exception....' + str(e)
    finally:
        moncon.disconnect()
        print 'Registering %d workers ended' % (len(workers),)
        # gevent.joinall(workers)
    gevent.spawn(monitor_new_subscriptions, timeout)
    gevent.spawn(monitor_new_submissions)

def stats(env, start_response):
    import datetime
    if env['PATH_INFO'] == '/':
        def subhtml(subscription):
            dct = subscription
            dct['lastDoc'] = datetime.datetime.fromtimestamp(subscription['lastChecked_']).isoformat(' ')
            return """<td>%(id)s</td>
<td>%(patientId)s</td>
<td>%(careProvisionCode)s</td>
<td>%(endpoint_)s</td>
<td>%(lastDoc)s</td>
""" % dct
        start_response('200 OK', [('Content-Type', 'text/html;charset=utf-8')])
        ws = "\n".join(["<tr class='%s'>%s</tr>" % ('active' if i.checking else 'inactive',  subhtml(i.subscription))
                        for k, i in workers.items()])
        str = """<html><head>
<meta http-equiv="refresh" content="5" > 
<style type="text/css">
tr.active td {
	background-color: #CC9999; color: black;
}
</style>
</head>
<body>
<h1>PCC Update Broker Server</h1>
<table border="1">
<tr>
<th>id</th>
<th>Patient id</th>
<th>Care Provision Code</th>
<th>Clbk Endpoint</th>
<th>Creation date of doc last checked</th>
</tr>
%s
</table>
</body>
</html>""" % ws
        return [str.encode('utf-8')]
    else:
        start_response('404 Not Found', [('Content-Type', 'text/html')])
        return ['<h1>Not Found</h1>']


if __name__ == "__main__":
    s = wsgi.WSGIServer(('', 9081), stats)
    s.start()
    gevent.spawn(schedule_all, 5*60)
    print 'Serving stats on 9081...'
    s.serve_forever()
