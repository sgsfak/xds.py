#!/usr/bin/python
from __future__ import with_statement
"""
You probably need to change some Configuration variables you can
find below...

---8<---

Requires:
  * gevent (http://www.gevent.org/)
  * lxml (http://codespeak.net/lxml/)
  * pymongo -- Python driver for MongoDB <http://www.mongodb.org>
"""
__author__ = "Stelios Sfakianakis <ssfak@ics.forth.gr>"
from gevent import monkey; monkey.patch_all()
from gevent import wsgi
from gevent import Greenlet
import gevent
from gevent.event import Event
import pymongo
from pymongo import objectid
import bson
import os
from lxml import etree
import sys
import urllib2
import json
import uuid

# Configuration!!
MONGO_HOST = '139.91.190.45'
REDIS_HOST = '139.91.190.41'

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
    pertInfo = "\n".join(["<pertinentInformation3>%s</pertinentInformation3>" % etree.tostring(x, xml_declaration=False) 
                          for x in entries])
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
%s
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
                           pertInfo,
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
    # print 'SENDING\n', soap
    with open("pcc-10.xml", "wb") as log:
        log.write(soap)
    try:
        fp = urllib2.urlopen(req)
        response = fp.read()
        print 'SUBMITTED AND GOT\n',response
    except urllib2.HTTPError, ex:
        msg = ex.read()
        print "PCC10 Error: %s %s" % (ex.code, msg)
        raise ex
    except urllib2.URLError, ex:
        print "PCC10 Error: %s " % (ex.reason)
    except:
        print "PCC10 Unexpected error:", sys.exc_info()[0]
        raise

class SubscriptionLet(Greenlet):
    def __init__(self, subscription, timeout = 30):
        gevent.Greenlet.__init__(self)
        self.subscription = subscription
        self.timeout = timeout
        self._ev = Event()
        self.checking = False
        self.stopped = False

    def id(self):
        return self.subscription.get('id')

    def wakeup(self):
        self._ev.set()
        
    def stop(self):
        self.stopped = True
        self._ev.set()
        
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
        # print '[%s] Now at subscr' % id, self.subscription
        entries = []
        moncon = pymongo.Connection(MONGO_HOST)
        try:
            docsdb = moncon.xds.docs
            lastUpdated = subscription['lastChecked_']
            endpoint = subscription.get('endpoint_') or 'http://example.org/'
            patientId = subscription['patientId']
            query = {'patientId':patientId, 'mimeType': 'text/xml', 'storedAt_':{'$gt': lastUpdated}}
            careRecordTimePeriod = subscription.get('careRecordTimePeriod')
            # if careRecordTimePeriod is not None:
            #    query['creationTime'] = {'$gte':careRecordTimePeriod['low'], 
            #                             '$lte':careRecordTimePeriod['high']}
            # clinicalStatementTimePeriod = subscription.get('clinicalStatementTimePeriod')
            # if clinicalStatementTimePeriod is not None:
            #    query['creationTime'] = {'$gte':clinicalStatementTimePeriod['low'], 
            #                             '$lte':clinicalStatementTimePeriod['high']}
            print '[%s] MONQ=%s' % (id, query)
            crs = docsdb.find(query, fields=['filename', 'storedAt_'], 
                              sort=[('storedAt_', pymongo.ASCENDING)])
            tm = None
            for d in crs:
                print '-->', d['filename']
                doc = None
                with open('static'+os.sep+d['filename'], 'rb') as fp:
                    doc = etree.parse(fp).getroot()
                e = self.match_subscription(doc)
                entries.extend(e)
                tm = d['storedAt_']
            print "[%s] Entries Found: %d" % (id, len(entries))
            if len(entries) > 0:
                send_pcc10(self.subscription, entries)
            if tm:
                subscription['lastChecked_'] = tm
                moncon.xds.pcc.update({'_id':objectid.ObjectId(self.id())},
                                      {"$set": {"lastChecked_": tm}})
        finally:
            moncon.disconnect()
        return entries
    def __str__(self):
        cpc = self.subscription.get('careProvisionCode')
        if cpc is None:
            cpc = ""
        return "[%s] Subscription (%s)" % (self.id(), self.subscription)

    def _run(self):
        id = self.id()
        print "[%s] SubscriptionLet starting.." % id
        while True:
            try:
                self.checking = True
                self.check_subscription()
            except Exception, ex:
                print "[%s] Oh no! just got: %s" % (id, ex)
                raise
            finally:
                self.checking = False
                print "[%s] Going to sleep for %d secs ..." % (id, self.timeout)
                op = self._ev.wait(timeout=self.timeout)
                if op:
                    self._ev.clear()
                    if self.stopped :
                        break

workers = {}
from collections import defaultdict
workers_per_patient = defaultdict(list)

NOTIFY_PORT = 9082
def handle_notification(conn, timeout):
    bufsize = 4096
    data = conn.recv(bufsize)
    # BSON provides the length of the msg in int32 litle-endian
    import struct
    ln = struct.unpack("<i", data[:4])[0]
    # print "len=%d expecting %s" % (len(data), ln)
    while len(data) < ln:
        data += conn.recv(bufsize)
    conn.close()
    msg = bson.BSON(data).decode()
    sub = msg.get('payload', '')
    op = msg.get('type', 'noop')
    if op == 'subscription':
        subid = sub['id']
        print '****** Got New subscription:', sub
        if workers.has_key(subid):
            return
        g = SubscriptionLet(sub, timeout)
        workers[subid] = g
        workers_per_patient[sub['patientId']].append(g)
        g.start()
    elif op == 'submission':
        patId = sub['patientId']
        print "****** Got New submission set for patient='%s'" % patId
        for g in workers_per_patient.get(patId, []):
            g.wakeup()

def listen_for_new_info(timeout):
    from socket import socket, AF_INET, SOCK_STREAM
    addr = ('localhost',NOTIFY_PORT)
    sock = socket(AF_INET, SOCK_STREAM)
    try:
        sock.bind(addr)
        sock.listen(5)
    except socket.error, msg:
        print "ERROR (listen_for_new_info): %s" % msg
        return
    # Receive messages
    print "LISTENING on",NOTIFY_PORT,"(TCP) for new submissions and subscriptions"
    while 1:
	conn,addr = sock.accept()
        gevent.spawn(handle_notification, conn, timeout)
    # Close socket
    sock.close()

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
    gevent.spawn(listen_for_new_info, timeout)

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

def test_event():
    if len(workers) > 0:
        print "waking up..."
        workers.items()[0][1].wakeup()

    
if __name__ == "__main__":
    s = wsgi.WSGIServer(('', 9081), stats)
    s.start()
    gevent.spawn(schedule_all, 30*60)
    print 'Serving stats on 9081...'
    s.serve_forever()
