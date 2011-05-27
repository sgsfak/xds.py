#!/usr/bin/python
from __future__ import with_statement
"""
This is a small XDS.b IHE compliant REgistry and Repository server
The Repository is actually the filesystem (the static directory)
while the Registry stores the documents and submission sets metadata
in a MongoDB json database server.

You probably need to change some Configuration variables you can
find below...

---8<---

Requires:
  * cherrypy (http://www.cherrypy.org/)
  * lxml (http://codespeak.net/lxml/)
  * pymongo -- Python driver for MongoDB <http://www.mongodb.org>
"""
__author__ = "Stelios Sfakianakis <ssfak@ics.forth.gr>"

import cherrypy
# import web
import email
import email.parser
import uuid
from lxml import etree
import pymongo
import hashlib
import time
import base64
import os
import sys
import tempfile
import json
import bson
import socket
from optparse import OptionParser
import random
# import mongo_utils
from xds_config import *

NS = {"soap":"http://www.w3.org/2003/05/soap-envelope", 
      "wsa":"http://www.w3.org/2005/08/addressing",
      "xdsb":"urn:ihe:iti:xds-b:2007",
      "rs":"urn:oasis:names:tc:ebxml-regrep:xsd:rs:3.0",
      "lcm":"urn:oasis:names:tc:ebxml-regrep:xsd:lcm:3.0",
      "rim":"urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0",
      "query":"urn:oasis:names:tc:ebxml-regrep:xsd:query:3.0",
      "xop":"http://www.w3.org/2004/08/xop/include",
      'hl7':'urn:hl7-org:v3',
      'xmlmime': 'http://www.w3.org/2004/11/xmlmime'
      ,'wsnt': 'http://docs.oasis-open.org/wsn/b-2'
      }

# The actions for the supported XDS transactions
PNR_XDS_OP = 'urn:ihe:iti:2007:ProvideAndRegisterDocumentSet-b'
SQ_XDS_OP = 'urn:ihe:iti:2007:RegistryStoredQuery'
RETR_XDS_OP = 'urn:ihe:iti:2007:RetrieveDocumentSet'

# PnR Submission Set 
# (see <http://goo.gl/mppj>)
SSET_CLASS_NODE = "urn:uuid:a54d6aa5-d40d-43f9-88c5-b4633d873bdd"
AUTHOR_SSET_CLASS = "urn:uuid:a7058bb9-b4e4-4307-ba5b-e3f0ab85e12d"
CT_SSET_CLASS = "urn:uuid:aa543740-bdda-424e-8c96-df4873be8500"

# Identification schemes UUIDs
# See also <http://goo.gl/8lfE>
UNIQID_SSET_SCHEME = "urn:uuid:96fdda7c-d067-4183-912e-bf5ee74998a8"
SRCID_SSET_SCHEME = "urn:uuid:554ac39e-e3fe-47fe-b233-965d2a147832"
PATID_SSET_SCHEME = "urn:uuid:6b5aea1a-874d-4603-a4bc-96a0a7b38446"

CLASSIFICATION_OBJTYPE = 'urn:oasis:names:tc:ebxml-regrep:ObjectType:RegistryObject:Classification'
EXTERNID_OBJTYPE = 'urn:oasis:names:tc:ebxml-regrep:ObjectType:RegistryObject:ExternalIdentifier'
REGPACKGE_OBJTYPE = "urn:oasis:names:tc:ebxml-regrep:ObjectType:RegistryObject:RegistryPackage"

# For document entries
DOC_OBJTYPE = "urn:uuid:7edca82f-054d-47f2-a032-9b2a5b5186c1"
CLCODE_DOC_CLASS = "urn:uuid:41a5887f-8865-4c09-adf7-e362475b143a"
AUTHOR_DOC_CLASS = "urn:uuid:93606bcf-9494-43ec-9b4e-a7748d1a838d"
CONFCODE_DOC_CLASS = "urn:uuid:f4f85eac-e6cb-4883-b524-f2705394840f"
EVCODE_DOC_CLASS = "urn:uuid:2c6b8cb7-8b2a-4051-b291-b1ae6a575ef4"
FMTCODE_DOC_CLASS = "urn:uuid:a09d5840-386c-46f2-b5ad-9c3699a4309d"
HCTC_DOC_CLASS = "urn:uuid:f33fb8ac-18af-42cc-ae0e-ed0b0bdb91e1"
PRCTC_DOC_CLASS = "urn:uuid:cccf5598-8b07-4b77-a05e-ae952c785ead"
TC_DOC_CLASS = "urn:uuid:f0306f51-975f-434e-a61c-c59651d33983"

PATID_DOC_SCHEME = "urn:uuid:58a6f841-87b3-4a3e-92fd-a8ffeff98427"
UNIQID_DOC_SCHEME = "urn:uuid:2e82c1f6-a085-4c72-9da3-8640a32e42ab"

# For Folders
FLD_OBJTYPE = "urn:uuid:d9d542f3-6cc4-48b6-8870-ea235fbc94c2"
CODEL_FLD_CLASS = "urn:uuid:1ba97051-7806-41a8-a48b-8fce7af683c5"
PATID_FLD_SCHEME = "urn:uuid:f64ffdf0-4b97-4e06-b79f-a52b38ec2f8a"
UNIQID_FLD_SCHEME = "urn:uuid:75df8f67-9973-4fbe-a900-df66cefecc5a"

#For Relationships
APND_CLASS = "urn:uuid:917dc511-f7da-4417-8664-de25b34d3def"
RPLC_CLASS = "urn:uuid:60fd13eb-b8f6-4f11-8f28-9ee000184339"
XFRM_CLASS = "urn:uuid:ede379e6-1147-4374-a943-8fcdcf1cd620"
XFRM_RPLC_CLASS = "urn:uuid:b76a27c7-af3c-4319-ba4c-b90c1dc45408"
SIGNS_CLASS = "urn:uuid:8ea93462-ad05-4cdc-8e54-a8084f6aff94"

HASMEM_ASSOCTYPE = "urn:oasis:names:tc:ebxml-regrep:AssociationType:HasMember"
RPLC_ASSOCTYPE = "urn:ihe:iti:2007:AssociationType:RPLC"

# A quick (?) way to get (the first of) my IP address
MYIP = socket.gethostbyname_ex(socket.gethostname())[2][0]

def get_author(xml, scheme, obj):
        def cons_auth(class_xml):
                auth = {}
                auth['authorPerson'] = get_slot_single(class_xml, 'authorPerson')
                auth['authorInstitution'] =  get_slot_multi(class_xml, 'authorInstitution')
                auth['authorRole'] = get_slot_multi(class_xml, 'authorRole')
                auth['authorSpecialty'] = get_slot_multi(class_xml, 'authorSpecialty')
                return auth
        l = xml.xpath("//rim:Classification[@classificationScheme='%s' and @classifiedObject='%s']"%
                      (scheme, obj), namespaces=NS)
        if len(l)==0: return None
        return [cons_auth(class_xml) for class_xml in l]

def get_classification_multi(xml, scheme, obj):
        def cons_code(c):
                (cs,) = c.xpath("rim:Slot[@name='codingScheme']/rim:ValueList/rim:Value", namespaces=NS)
                cd = c.attrib['nodeRepresentation']
                return {"codingScheme":cs.text, "code":cd}
        l = xml.xpath("//rim:Classification[@classificationScheme='%s' and @classifiedObject='%s']"%
                      (scheme, obj), namespaces=NS)
        return [cons_code(i) for i in l]

def xml_authors(xml, scheme, authrs, clObj):
        RIM = "{%s}" % NS['rim']
        authors = authrs if type(authrs) == list else [authrs]
        for author in authors:
                c  = etree.SubElement(xml, RIM+"Classification",
                                      attrib={'id': uuid.uuid4().urn, 
                                              'objectType':CLASSIFICATION_OBJTYPE,
                                              'classificationScheme': scheme,
                                              'classifiedObject': clObj,
                                              'nodeRepresentation':'',
                                              'home':''
                                              })
                for k in author.keys():
                        xml_slot(c, k, author[k])
                n = etree.SubElement(c, RIM+"Name")
                d = etree.SubElement(c, RIM+"Description")
                v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})

def xml_slot(xml, name, values):
        if values is None:
                return
        vs = values if type(values) == list else [values]
        if len(vs) == 0:
                return
        RIM = "{%s}" % NS['rim']
        s = etree.SubElement(xml, RIM+"Slot", attrib={'name':name})
        vl = etree.SubElement(s, RIM+"ValueList")
        for v in vs:
                vt = etree.SubElement(vl, RIM+"Value")
                vt.text = "%s"%v

def xml_classification(xml, scheme, codes, clObj):
        if codes is None: 
                return
        RIM = "{%s}" % NS['rim']
        cds = codes if type(codes)==list else [codes]
        for coded in cds:
                c  = etree.SubElement(xml, RIM+"Classification",
                                      attrib={'id': uuid.uuid4().urn,
                                              'objectType':CLASSIFICATION_OBJTYPE,
                                              'classificationScheme': scheme,
                                              'classifiedObject': clObj,
                                              'nodeRepresentation':coded['code'],
                                              'home':''
                                              })
                xml_slot(c, 'codingScheme', coded['codingScheme'])
                n = etree.SubElement(c, RIM+"Name")
                ls = etree.SubElement(n, RIM+"LocalizedString", attrib={'value':coded['code']})
                d = etree.SubElement(c, RIM+"Description")
                v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})

def xml_external_id(xml, scheme, name, value, idObj):
        if value is None: return
        RIM = "{%s}" % NS['rim']
        c  = etree.SubElement(xml, RIM+"ExternalIdentifier",
                              attrib={'id': uuid.uuid4().urn,
                                      'objectType':EXTERNID_OBJTYPE,
                                      'identificationScheme':scheme,
                                      'value':value,
                                      'registryObject':idObj,
                                      'home':''
                                      })
        n = etree.SubElement(c, RIM+"Name")
        l=etree.SubElement(n, RIM+"LocalizedString", 
                           attrib={'{http://www.w3.org/XML/1998/namespace}lang':'en-US',
                                   'value':name})
        d = etree.SubElement(c, RIM+"Description")
        v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})


def xml_document(xml, doc):
        RIM = "{%s}" % NS['rim']
        def add_slots(xml, nms):
                for n in nms:
                        if n in doc: xml_slot(xml, n, doc[n])
        id = doc['entryUUID']
        c  = etree.SubElement(xml, RIM+"ExtrinsicObject",
                              attrib={'id': id,
                                      'lid': id,
                                      'objectType':DOC_OBJTYPE,
                                      'status':'urn:oasis:names:tc:ebxml-regrep:StatusType:'+doc.get('availabilityStatus'),
                                      'mimeType':doc['mimeType'],
                                      'isOpaque':'false',
                                      'home':''
                                      })
        add_slots(c, ['URI', 'creationTime', 'hash', 'languageCode', 
                      'repositoryUniqueId','serviceStartTime','serviceStopTime'
                      ,'size', 'sourcePatientId', 'sourcePatientInfo'
                      ,'legalAuthenticator'])
        n = etree.SubElement(c, RIM+"Name")
        d = etree.SubElement(c, RIM+"Description")
        v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})
        xml_authors(c, AUTHOR_DOC_CLASS, doc.get('author'), id) 
        xml_classification(c, CLCODE_DOC_CLASS, doc.get('classCode'), id)
        xml_classification(c, CONFCODE_DOC_CLASS, doc.get('confidCode'), id)
        xml_classification(c, FMTCODE_DOC_CLASS, doc.get('formatCode'), id)
        xml_classification(c, EVCODE_DOC_CLASS, doc.get('eventCodeList'), id)
        xml_classification(c, TC_DOC_CLASS, doc.get('typeCode'), id)
        xml_classification(c, HCTC_DOC_CLASS, doc.get('healthcareFacilityTypeCode'), id)
        xml_classification(c, PRCTC_DOC_CLASS, doc.get('practiceSettingCode'), id)
        
        xml_external_id(c, PATID_DOC_SCHEME, 'XDSDocumentEntry.patientId', doc['patientId'], id)
        xml_external_id(c, UNIQID_DOC_SCHEME, 'XDSDocumentEntry.uniqueId', doc['uniqueId'], id)

def xml_submission(xml, doc):
        RIM = "{%s}" % NS['rim']
        def add_slots(xml, nms):
                for n in nms:
                        if n in doc: xml_slot(xml, n, doc[n])
        id = doc['entryUUID']
        c  = etree.SubElement(xml, RIM+"RegistryPackage",
                              attrib={'id': id,
                                      'lid': id,
                                      'objectType':REGPACKGE_OBJTYPE,
                                      'status':'urn:oasis:names:tc:ebxml-regrep:StatusType:Approved'
                                      })
        add_slots(c, ['submissionTime', 'intendedRecipient'])
        n = etree.SubElement(c, RIM+"Name")
        d = etree.SubElement(c, RIM+"Description")
        v = etree.SubElement(c, RIM+"VersionInfo", attrib={'versionName':'1.1'})
        xml_authors(c, AUTHOR_SSET_CLASS, doc.get('author'), id) 
        xml_classification(c, CT_SSET_CLASS, doc.get('contentTypeCode'), id)
        cc  = etree.SubElement(c, RIM+"Classification",
                               attrib={'id': uuid.uuid4().urn,
                                       'objectType':CLASSIFICATION_OBJTYPE,
                                       'classifiedObject': id,
                                       'classificationNode':"urn:uuid:a54d6aa5-d40d-43f9-88c5-b4633d873bdd"
                                       })
        n = etree.SubElement(cc, RIM+"Name")
        d = etree.SubElement(cc, RIM+"Description")
        v = etree.SubElement(cc, RIM+"VersionInfo", attrib={'versionName':'1.1'})
        xml_external_id(c, PATID_SSET_SCHEME, 'XDSSubmissionSet.patientId', doc['patientId'], id)
        xml_external_id(c, UNIQID_SSET_SCHEME, 'XDSSubmissionSet.uniqueId', doc['uniqueId'], id)
        xml_external_id(c, SRCID_SSET_SCHEME, 'XDSSubmissionSet.sourceId', doc['sourceId'], id)

def get_classification(xml, scheme, obj):
        l = get_classification_multi(xml, scheme, obj)
        if len(l)==0: return None
        return l[0]

def get_external_id(xml, scheme, obj):
        l = xml.xpath("//rim:ExternalIdentifier[@identificationScheme='%s' and @registryObject='%s']"%
                      (scheme, obj), namespaces=NS)
        if len(l)==0: return None
        (c,) = l
        return c.attrib['value']

def get_slots(o):
        sl = {}
        for s in o.xpath("rim:Slot", namespaces=NS):
                sl[s.attrib["name"]] = [v.text for v in s.xpath("rim:ValueList/rim:Value", namespaces=NS)]
        return sl

def get_slot_multi(o, name):
        vls = o.xpath("rim:Slot[@name='%s']/rim:ValueList/rim:Value"% name, 
                      namespaces=NS)
        return [v.text for v in vls]

def get_slot_single(o, name):
        vls = get_slot_multi(o, name)
        if len(vls) > 0: return vls[0]
        return None

def parse_provide_and_register(xml):
        # See also http://ihewiki.wustl.edu/wiki/index.php/Metadata_Patterns
        # record the current timestamp
        now = time.time()
        savdir = os.sep.join(["%02d" % i for i in time.gmtime(now)[:3]])+os.sep
        savdirURI = "/".join(["%02d" % i for i in time.gmtime(now)[:3]])+"/"
        cl = xml.xpath("//lcm:SubmitObjectsRequest/rim:RegistryObjectList/rim:Classification[@classificationNode='%s']"%SSET_CLASS_NODE, 
                       namespaces=NS)[0]
        sId = cl.get("classifiedObject")
        rp = xml.xpath("//rim:RegistryPackage[@id='%s']" % sId, namespaces=NS)[0]
        sUUID = sId
        if not sUUID.startswith("urn:uuid:"): sUUID = uuid.uuid4().urn
        sset = {"storedAt_":now}
        sset["entryUUID"] = sUUID
        sset["submissionTime"] = get_slot_single(rp, "submissionTime")
        sset["intendedRecipient"] = get_slot_multi(rp, "intendedRecipient")
        f = get_external_id(xml, UNIQID_SSET_SCHEME, sId)
        sset["uniqueId"] = f
        f = get_author(xml, AUTHOR_SSET_CLASS, sId)
        if f: sset["author"] = f
        f = get_classification(xml, CT_SSET_CLASS, sId)
        if f: sset["contentTypeCode"] = f
        f = get_external_id(xml, PATID_SSET_SCHEME, sId)
        sset["patientId"] = f
        f = get_external_id(xml, SRCID_SSET_SCHEME, sId)
        sset["sourceId"] = f
        members = xml.xpath("//rim:Association[@associationType='%s' and @sourceObject='%s']/@targetObject" % 
                            (HASMEM_ASSOCTYPE, sId), namespaces=NS)
        sset["docs"] = {}
        for dId in members:
                l = xml.xpath("//rim:ExtrinsicObject[@id='%s']"%dId, namespaces=NS)
                if l is None or len(l)==0: continue
                eo = l[0]
                # (cid,) = xml.xpath("//xdsb:Document[@id='%s']/xop:Include/@href" % dId, namespaces=NS)
                # cid = "<%s>" % cid[4:]
                docen = {"storedAt_":now}
                docen["availabilityStatus"]="Approved"
                f = get_author(xml, AUTHOR_DOC_CLASS, dId)
                if f: docen["author"] = f
                f = get_classification(xml, CLCODE_DOC_CLASS, dId)
                if f: docen["classCode"] = f
                f = get_slot_single(eo, "creationTime")
                if f: docen["creationTime"] = f
                dUUID = dId
                if not dUUID.startswith("urn:uuid:"): dUUID = uuid.uuid4().urn
                docen["entryUUID"] = dUUID
                docen["eventCodeList"] = get_classification_multi(xml, EVCODE_DOC_CLASS, dId)
                f = get_classification(xml, CONFCODE_DOC_CLASS, dId)
                if f: docen["confidCode"] = f
                f = get_classification(xml, FMTCODE_DOC_CLASS, dId)
                if f: docen["formatCode"] = f
                f = get_classification(xml, HCTC_DOC_CLASS, dId)
                if f: docen["healthcareFacilityTypeCode"] = f
                f = get_slot_single(eo, "languageCode")
                if f: docen["languageCode"] = f
                f = get_slot_single(eo, "legalAuthenticator")
                if f: docen["legalAuthenticator"] = f
                docen["mimeType"] = eo.get("mimeType")
                docen["patientId"] = get_external_id(xml, PATID_DOC_SCHEME, dId)
                f = get_classification(xml, PRCTC_DOC_CLASS, dId)
                if f: docen["practiceSettingCode"] = f
                docen["repositoryUniqueId"] = MY_REPO_ID
                f = get_slot_single(eo, "serviceStartTime")
                if f: docen["serviceStartTime"] = f
                f = get_slot_single(eo, "serviceStopTime")
                if f: docen["serviceStopTime"] = f
                f = get_slot_single(eo, "size")
                if f: docen["size"] = f
                f = get_slot_single(eo, "sourcePatientId")
                if f: docen["sourcePatientId"] = f
                docen["sourcePatientInfo"] = get_slot_multi(eo, "sourcePatientInfo")
                docen["typeCode"] = get_classification(xml, TC_DOC_CLASS, dId)
                docen["uniqueId"] = get_external_id(xml, UNIQID_DOC_SCHEME, dId)
                fn = dUUID[9:] + guess_suffix(docen['mimeType'])
                docen["filename"] = savdir + fn
                docen["URI"] = cherrypy.request.base + "/xdsdocs/" + savdirURI + fn
                docen["inSubmissionUUID"] = sUUID
                sset["docs"][dId] = docen
        return sset

SUFFIXES_FOR_TYPES = {
        'application/pdf': 'pdf',
        'text/xml': 'xml',
        'text/html': 'html',
        'text/plain': 'txt',
        'application/xml': 'xml',
        'application/xhtml': 'xhtml',
        'image/gif' : 'gif',
        'image/png' : 'png',
        'image/jpeg' : 'jpg'
        }
def guess_suffix(ct):
        if ct in SUFFIXES_FOR_TYPES: return "."+SUFFIXES_FOR_TYPES[ct]
        return ''

def parse_content_type(ct):
        s = "content_type="+ct
        v = [t.strip() for t in s.split(';')]
        return dict([tuple(l.split('=', 1)) for l in v])

SUCCESS_RESULT_STATUS = "urn:oasis:names:tc:ebxml-regrep:ResponseStatusType:Success"
FAILURE_RESULT_STATUS = "urn:oasis:names:tc:ebxml-regrep:ResponseStatusType:Failure"

def handle_mtom_oper(moncon, msg):
        from lxml import etree
        msgs = msg.get_payload()
        xml = msgs[0].get_payload()
        root = etree.fromstring(xml)
        wact = root.xpath("/soap:Envelope/soap:Header/wsa:Action", 
                          namespaces=NS)[0]
        wmesgid = root.xpath("/soap:Envelope/soap:Header/wsa:MessageID", 
                             namespaces=NS)[0].text
        oper = wact.text
        resAct = oper + "Response"
        body = root.xpath("/soap:Envelope/soap:Body", namespaces=NS)[0]
        print "---> TRANSACTION: " , oper[oper.rfind(':')+1:]
        if oper == PNR_XDS_OP:#w is not None:
                attached = dict([(m['Content-ID'].strip(), m) for m in msgs[1:]])
                docs_data = {}
                for xml_doc in body.xpath("//xdsb:Document", namespaces=NS):
                        xop = xml_doc.xpath("xop:Include/@href", namespaces=NS)
                        if len(xop) == 1:
                                cid = "<%s>" % xop[0].strip()[4:]
                                m = attached.get(cid)
                                data = m.get_payload(decode=True)
                        else:
                                data = base64.b64decode(xml_doc.text)
                        dId = xml_doc.attrib['id']
                        tmpfp, tmpfn = tempfile.mkstemp()
                        c = os.write(tmpfp, data)
                        os.close(tmpfp)
                        docs_data[dId] = {'tmpfn': tmpfn, 'size':c,
                                          'hash': hashlib.sha1(data).hexdigest()}
                attached = None
                msg = None
                sset = parse_provide_and_register(body)
                docs = sset["docs"]
                sset["docs"] = []
                mongoId = None
                try:
                        for dId,doc in docs.items():
                                doc_data = docs_data[dId]
                                fn  = "static"+os.sep+doc["filename"]
                                os.renames(doc_data['tmpfn'], fn)
                                print "wrote ", fn
                                doc['size'] = doc_data['size']
                                doc["hash"] = doc_data['hash']
                                moncon.xds.docs.insert(doc, safe=True)
                                sset['docs'].append(doc['entryUUID'])
                                print 'Document',doc['entryUUID'], 'inserted'
                        mongoId = moncon.xds.ssets.insert(sset, safe=True)
                        print 'submission',sset['entryUUID'], 'inserted'
                except Exception, ex:
                        print "ERROR: %s" % ex
                        resultStatus = FAILURE_RESULT_STATUS
                else:
                        resultStatus = SUCCESS_RESULT_STATUS
                        # 
                        # Send notification to the UpdateBroker for the newly 
                        # 
                        sset['id'] = str(mongoId)
                        del sset['_id']
                        send_submission_notification(sset) #send_notification('submission', sset)
                        print "NEW SUBMISSION PUSHED TO UB"
                finally:
                        moncon.end_request()
                RS = NS['rs']
                res = etree.Element("{%s}RegistryResponse" % RS)
                res.attrib['status'] = resultStatus
                soapMsg = build_soap_msg(resAct, wmesgid, res)
                ret = generate_mtom(soapMsg, resAct)
                #print ret
                return ret
        elif oper == RETR_XDS_OP:
                elems = body.xpath("xdsb:RetrieveDocumentSetRequest/xdsb:DocumentRequest/xdsb:DocumentUniqueId", namespaces=NS)
                docUids = [e.text for e in elems]
                print docUids
                toRetrieve = []
                RS = NS['rs']
                XDSB = NS['xdsb']
                res = etree.Element("{%s}RetrieveDocumentSetResponse" % XDSB)
                resultStatus = SUCCESS_RESULT_STATUS
                from email.utils import make_msgid
                try:
                        for uid in docUids:
                                doc = moncon.xds.docs.find_one({"uniqueId": uid}, {"filename":1, "mimeType":1})
                                if not doc:
                                        print "Requested doc with uid ",uid, " was not found! (ignoring)"
                                        resultStatus = FAILURE_RESULT_STATUS
                                else:
                                        cid = make_msgid()
                                        toRetrieve.append({"uid":uid, 
                                                           "fn":'static' + os.sep + doc['filename'], 
                                                           "cid":cid, 
                                                           "mt":doc['mimeType']})
                        for tr in toRetrieve:
                                e = etree.SubElement(res,"{%s}DocumentResponse"%(XDSB,))
                                e1 = etree.SubElement(e, "{%s}RepositoryUniqueId"%(XDSB,))
                                e1.text = MY_REPO_ID
                                e2 = etree.SubElement(e, "{%s}DocumentUniqueId"%(XDSB,))
                                e2.text = tr['uid']
                                e3 = etree.SubElement(e, "{%s}mimeType"%(XDSB,))
                                e3.text = tr['mt']
                                d = etree.SubElement(e, "{%s}Document"%(XDSB,))
                                x = etree.SubElement(d, "{%s}Include"%(NS['xop'],))
                                x.attrib['href']="cid:"+tr['cid'].strip('<>')
                except Exception, ex:
                        print "ERROR: %s" % ex
                        resultStatus = FAILURE_RESULT_STATUS
                finally:
                        moncon.end_request()
                rr = etree.Element("{%s}RegistryResponse" % RS)
                rr.attrib['status'] = resultStatus
                res.insert(0, rr)
                soapMsg = build_soap_msg(resAct, wmesgid, res)
                ret = generate_mtom(soapMsg, resAct, toRetrieve)
                #print ret
                return ret
        return None 

def build_soap_msg(action, relMsg, body):
        SOAP = "{%s}" % NS['soap']
        WSA = "{%s}" % NS['wsa']
        env = etree.Element(SOAP+"Envelope", nsmap=NS)
        hdr = etree.SubElement(env, SOAP+"Header")
        act = etree.SubElement(hdr, WSA+"Action")
        act.set(SOAP+"mustUnderstand", "true")
        act.text = action
        rel = etree.SubElement(hdr, WSA+"RelatesTo")
        rel.text = relMsg
        bd = etree.SubElement(env, SOAP+"Body")
        bd.append(body)
        return env
        
def generate_mtom(xml_part, resAct, docs=[]):
        result = etree.tostring(xml_part, pretty_print=False, 
                                encoding='UTF-8',
                                #encoding='ISO-8859-1',
                                xml_declaration=True)
        from email.utils import make_msgid
        cid = make_msgid()
        boundary = "5s1t9e5l8i3o0s6r4u8l1e6s1.6.2.1.2.8"
        mtom_ct = "multipart/related; action=\"%s\"; start-info=\"application/soap+xml\"; type=\"application/xop+xml\"; start=\"%s\";boundary=\"%s\"" % (resAct, cid, boundary)
        cherrypy.response.headers['Content-type'] =  mtom_ct
        from cStringIO import StringIO
        out = StringIO()
        out.write("--%s\r\n" % boundary)
        out.write('Content-Type: application/xop+xml;type="application/soap+xml"\r\n')
        out.write('Content-Transfer-Encoding: binary\r\n')
        out.write("Content-ID: %s\r\n\r\n" % cid)
        out.write(result)
        # with open('mtom_soap_out.xml', 'wb') as fout: fout.write(result)
        for d in docs:
                out.write("\r\n--%s\r\n" % boundary)
                data = out.getvalue()
                out.close()
                yield data
                out = StringIO()
                out.write('Content-Type: application/octet-stream\r\n')
                out.write('Content-Transfer-Encoding: binary\r\n')
                out.write("Content-ID: %s\r\n\r\n" % d['cid'])
                with open(d['fn'], 'rb') as fp:
                        buf = fp.read(8*1024)
                        while not buf == '':
                                out.write(buf)
                                data = out.getvalue()
                                out.close()
                                yield data
                                out = StringIO()
                                buf = fp.read(8*1024)
        
        out.write("\r\n--%s--" % boundary)
        data = out.getvalue()
        out.close()
        yield data

FINDDOCUMENTS_SQ = "urn:uuid:14d4debf-8f97-4251-9a74-a90016b0af0d"
FINDSUBMISSIONSETS_SQ = "urn:uuid:f26abbcb-ac74-4422-8a30-edb644bbc1a9"
FINDFOLDERS_SQ = "urn:uuid:958f3006-baad-4929-a4de-ff1114824431"
GETALL_SQ = "urn:uuid:10b545ea-725c-446d-9b95-8aeb444eddf3"
GETDOCUMENTS_SQ = "urn:uuid:5c4f972b-d56b-40ac-a5fc-c8ca9b40b9d4"
GETFOLDERS_SQ = "urn:uuid:5737b14c-8a1a-4539-b659-e03a34a5e1e4"
GETASSOCIATIONS_SQ = "urn:uuid:a7ae438b-4bc2-4642-93e9-be891f7bb155"
GETDOCUMENTSANDASSOCIATIONS_SQ = "urn:uuid:bab9529a-4a10-40b3-a01f-f68a615d247a"
GETSUBMISSIONSETS_SQ = "urn:uuid:51224314-5390-4169-9b91-b1980040715a"
GETSUBMISSIONSETANDCONTENTS_SQ = "urn:uuid:e8e3cb2c-e39c-46b9-99e4-c12f57260b83"
GETFOLDERANDCONTENTS_SQ = "urn:uuid:b909a503-523d-4517-8acf-8e5834dfc4c7"
GETFOLDERSFORDOCUMENT_SQ = "urn:uuid:10cae35a-c7f9-4cf5-b61e-fc3278ffb578"
GETRELATEDDOCUMENTS_SQ = "urn:uuid:d90e5407-b356-4d91-a89f-873917b4b0e6"

def handle_simple_soap_oper(moncon, inp):
        root = etree.fromstring(inp)
        wact = root.xpath("/soap:Envelope/soap:Header/wsa:Action", 
                          namespaces=NS)[0]
        wmesgid = root.xpath("/soap:Envelope/soap:Header/wsa:MessageID", 
                             namespaces=NS)[0].text
        oper = wact.text
        resAct = oper + "Response"
        print '--> SO I got ', oper
        q = root.xpath("//query:AdhocQueryRequest", namespaces=NS)[0]
        refsOnly = q.xpath("query:ResponseOption/@returnType", 
                           namespaces=NS)[0] == 'ObjectRef'
        monSel = None
        if refsOnly: monSel=['entryUUID']
        sq = q.xpath("rim:AdhocQuery/@id", namespaces=NS)[0]
        if sq not in [GETDOCUMENTS_SQ, GETDOCUMENTSANDASSOCIATIONS_SQ, 
                        GETSUBMISSIONSETANDCONTENTS_SQ, FINDDOCUMENTS_SQ,
                        GETSUBMISSIONSETS_SQ, FINDSUBMISSIONSETS_SQ]:
                raise cherrypy.HTTPError(message="Sorry I don't support this (%s) type of query!" % sq)
        else:
                crit = {}
                for st in q.xpath("rim:AdhocQuery/rim:Slot", namespaces=NS):
                        n = st.attrib['name']
                        crit[n] = []
                        for vt in st.xpath("rim:ValueList/rim:Value",  namespaces=NS):
                                v = vt.text.strip()
                                if v.startswith('('):
                                        v = v[1:-1] # remove ( and )
                                        for a in v.strip().split(','):
                                                crit[n].append(a.strip().strip("'"))
                                else:
                                        crit[n].append(v.strip().strip("'"))
                print "CRITERIA : ", crit
                searchSubmissions = sq in [GETSUBMISSIONSETS_SQ, GETSUBMISSIONSETANDCONTENTS_SQ, FINDSUBMISSIONSETS_SQ]
                monqry = {}
                for k,v in crit.items():
                        if k.endswith('UniqueId'):
                                monqry['uniqueId']= len(v)==1 and v[0] or {"$in":v}
                        elif k.endswith('EntryUUID'):
                                monqry['entryUUID']=len(v)==1 and v[0] or {"$in":v}
                        elif k.endswith('Status'):
                                monqry['availabilityStatus']=v[0][v[0].rfind(':')+1 :]
                        elif k.endswith('PatientId'):
                                monqry['patientId']=v[0]
                print "MONGO QUERY: ", monqry
                coll = searchSubmissions and moncon.xds.ssets or moncon.xds.docs
                QNS = "{%s}" % NS['query']
                RIM = "{%s}" % NS['rim']
                xml = etree.Element(QNS+"AdhocQueryResponse")
                xml.attrib['status'] = SUCCESS_RESULT_STATUS
                rob = etree.SubElement(xml, RIM+"RegistryObjectList")
                for doc in coll.find(monqry, monSel):
                        uid = doc['entryUUID']
                        print 'Found ', uid
                        if refsOnly:
                                r = etree.SubElement(rob, RIM+"ObjectRef", 
                                                     attrib={'home':'',
                                                             'id': uid})
                        else:
                                if searchSubmissions:
                                        xml_submission(rob, doc)
                                else:
                                        xml_document(rob, doc)
                moncon.end_request()
                soap = build_soap_msg(resAct, wmesgid, xml)
                response = etree.tostring(soap, pretty_print=False, 
                                          encoding='UTF-8',
                                          #encoding='ISO-8859-1',
                                          xml_declaration=True)
                # with open("simple_soap_out.xml", "wb") as fout: fout.write(response)
                cherrypy.response.headers['Content-type'] = 'application/soap+xml'
                return response

class XDS_Handler:
        exposed = True
        def __init__(self, mongoHost):
                self.con = pymongo.Connection(host=mongoHost)
        def GET(self):
                cherrypy.response.headers['Content-type'] = 'text/html'
                return ["""<p>This is an <a href='http://www.ihe.net/'>IHE</a>
<a href='http://ihewiki.wustl.edu/wiki/index.php/XDS_Main_Page'>XDS</a> Registry and Repository server. 
Some links to begin with:</p>
<ul>
<li><a href='http://www.ihe.net/Technical_Framework/index.cfm#IT'>IT Infrastructure Technical Framework</a></li>
<li><a href='http://wiki.ihe.net/index.php?title=XDS.b'>XDS implementation</a></li>
</ul>
<p>
 &copy; 2010-2011 FORTH-ICS All rights reserved.
"""]
        def POST(self):
                print "TE: "+cherrypy.request.headers.get('TRANSFER-ENCODING', "")
                headers = cherrypy.request.headers
                reqfile = cherrypy.request.rfile
                maxlen = 10 * 1024 * 1024
                ct = headers['Content-Type']
                print "GOT Content-type:",ct
                d = parse_content_type(ct)
                if d['content_type']=='multipart/related':
                    fp = email.parser.FeedParser()
                    fp.feed("Content-type: "+ct+"\r\n")
                    while True:
                        data = reqfile.read(4096)
                        if data == '':
                            break
                        fp.feed(data)
                    msg = fp.close()
                    for chunk in handle_mtom_oper(self.con, msg):
                        yield chunk
                else:
                    cl = int(headers.get('Content-Length', 0))
                    if cl == 0:
                        data = reqfile.read()
                    else:
                        data = reqfile.read(cl)
                    yield handle_simple_soap_oper(self.con, data)
                    
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
                        , '*':'*' #My extension to get all entries!!
                        }
# See <http://wiki.ihe.net/index.php?title=PCC-9>
class PCC9_Handler:
        exposed = True
        def __init__(self, mongoHost):
                self.con = pymongo.Connection(host=mongoHost)
        def GET(self):
                cherrypy.response.headers['Content-Type'] = 'text/html'
                return ["""<p>This is an <a href='http://www.ihe.net/'>IHE</a> PCC-CM server 
accepting PCC-9 messages. 
Some links to begin with:</p>
<ul>
<li><a href='http://wiki.ihe.net/index.php?title=PCC-9'>PCC-9</a></li>
<li><a href='http://wiki.ihe.net/index.php?title=PCC_TF-2'>PCC TF-2</a></li>
</ul>
<p>
 &copy; 2010-2011 FORTH-ICS All rights reserved.
"""]
        def POST(self):
                reqfile = cherrypy.request.rfile
                headers = cherrypy.request.headers
                cl = int(headers.get('Content-Length', 0))
                if cl == 0:
                    data = reqfile.read()
                else:
                    data = reqfile.read(cl)
                root = etree.fromstring(data)
                l = root.xpath('/soap:Envelope/soap:Header/wsa:ReplyTo/wsa:Address', namespaces=NS)
                if len(l) == 0:
                        # return 'Error, you need to send a wsa:ReplyTo/wsa:Address message'
                        endpoint = None
                else:
                        endpoint = l[0].text
                errors = []
                mongoId = None
                while True:
                        l = root.xpath('//hl7:QUPC_IN043100UV01', namespaces=NS)
                        if len(l) == 0:
                                errors.append({'code':'ILLEGAL', 'text': 'Error, you need to send a PCC 09 xml message'})
                                break
                        pcc9 = l[0]
                        l = pcc9.xpath('hl7:controlActProcess/hl7:queryByParameter/hl7:parameterList', namespaces=NS)
                        if len(l) == 0:
                                errors.append({'code':'ILLEGAL',
                                               'text': 'Error, you need to send a PCC 09 xml message (no parameter list!)'})
                                break
                        # SRDC Start
                        m = pcc9.xpath('hl7:controlActProcess/hl7:id/@extension', namespaces=NS)
			queryId = "0"
                        if len(m) == 0:
				t = l[0].xpath("hl7:careProvisionCode/hl7:value/@code", namespaces=NS)
				if len(t)==0:
                                        errors.append({'code':'ILLEGAL',
                                                       'text': 'Error, you need to send a PCC 09 xml message (no careProvisionCode!)'})
                                        break
                                if t[0] not in PCODES_TEMPLATE_IDS:
                                        errors.append({'code':'CODE_INVALID',
                                                       'text': 'careProvisionCode'})
                                        break
				if t[0] == "9279-1":
					queryId = 1
				elif t[0] == "COBSCAT":
					queryId = 2
				elif t[0] == "MEDCCAT":
					queryId = 3
				elif t[0] == "CONDLIST":
					queryId = 4
				elif t[0] == "PROBLIST":
					queryId = 5
				elif t[0] == "INTOLIST":
					queryId = 6
				elif t[0] == "RISKLIST":
					queryId = 7
				elif t[0] == "LABCAT":
					queryId = 8
				elif t[0] == "DICAT":
					queryId = 9
				elif t[0] == "RXCAT":
					queryId = 10
				elif t[0] == "MEDLIST":
					queryId = 11
				elif t[0] == "CURMEDLIST":
					queryId = 12
				elif t[0] == "DISCHMEDLIST":
					queryId = 13
				elif t[0] == "HISTMEDLIST":
					queryId = 14
				elif t[0] == "IMMUCAT":
					queryId = 15
				else:
					queryId = 16
                                queryId = str(queryId)
			else:
                                queryId = m[0]
			# SRDC End
                        con = None
                        worker_port = None
                        try:
                                pl = l[0]
                                subscription = {'endpoint_': endpoint, 'lastChecked_':0, 'queryId':queryId}
                                t = pl.xpath("hl7:careProvisionCode/hl7:value/@code", namespaces=NS)
                                if len(t)==0:
                                        errors.append({'code':'ILLEGAL',
                                                       'text': 'Error, you need to send a PCC 09 xml message (no careProvisionCode!)'})
                                        break
                                cpc = t[0]
                                # See http://goo.gl/qdty
                                if cpc not in PCODES_TEMPLATE_IDS:
                                        errors.append({'code':'CODE_INVALID',
                                                       'text': 'careProvisionCode'})
                                        break
                                subscription['careProvisionCode'] = cpc
                                t = pl.xpath('hl7:patientId/hl7:value/@extension', namespaces=NS)
                                if len(t) == 0:
                                        errors.append({'code':'ILLEGAL',
                                                       'text': 'No patientId given'})
                                        break
                                pid = t[0]                                                       
                                pidroot = pl.xpath('hl7:patientId/hl7:value/@root', namespaces=NS)
                                if len(pidroot) == 0: 
                                        pidroot = ''
                                else:
                                        pidroot = pidroot[0]
                                subscription['patientId'] = "%s^^^&%s&ISO" % (pid ,pidroot)
                                t = pl.xpath('hl7:patientName/hl7:value/hl7:given', namespaces=NS)
                                pat_fn = t[0].text if len(t)>0 else ''
                                t = pl.xpath('hl7:patientName/hl7:value/hl7:family', namespaces=NS)
                                pat_ln = t[0].text if len(t)>0 else ''
                                subscription['patientName'] = {'given':pat_fn, 'family':pat_ln}

                                t = pl.xpath("hl7:maximumHistoryStatements/hl7:value/@value", namespaces=NS)
                                subscription['maximumHistoryStatements'] = len(t)>0 and int(t[0]) or 50
                                t = pl.xpath('hl7:careRecordTimePeriod/hl7:value', namespaces=NS)
                                if len(t) != 0:
                                        low = t[0].xpath('hl7:low/@value', namespaces=NS)[0]
                                        high = t[0].xpath('hl7:high/@value', namespaces=NS)[0]
                                        if low > high:
                                                errors.append({'code':'FORMAT',
                                                               'text': 'careRecordTimePeriod'})
                                                break
                                        subscription['careRecordTimePeriod'] = {'low':low, 'high':high}
                                t = pl.xpath('hl7:clinicalStatementTimePeriod/hl7:value', namespaces=NS)
                                if len(t) != 0:
                                        low = t[0].xpath('hl7:low/@value', namespaces=NS)[0]
                                        high = t[0].xpath('hl7:high/@value', namespaces=NS)[0]
                                        if low > high:
                                                errors.append({'code':'FORMAT',
                                                               'text': 'clinicalStatementTimePeriod'})
                                                break
                                        subscription['clinicalStatementTimePeriod'] = {'low':low, 'high':high}
                                subscription['storedAt_'] = time.time()
                                coll = self.con.xds.pcc
                                mongoId = coll.insert( subscription, safe=True )
                                print "New subscription %s stored in DB" % mongoId
                                # 
                                # Send notification to the UpdateBroker through Redis
                                subscription['id'] = str(mongoId)
                                del subscription['_id']
                                worker_port = send_subscription_notification(subscription)
                                print "New subscription %s pushed to UB at %s" % (mongoId, worker_port)
                        except pymongo.errors.ConnectionFailure, ex:
                                print "MONGO DB connection failure!!"
                        except Exception, ex:
                                print "Unexpected error:", str(ex)
                                errors.append({'code':'ISSUE',
                                               'text': "Unexpected error:%s" % (ex,)})
                        finally:
                                self.con.end_request()
                        break
                cherrypy.response.headers['Content-Type'] = 'application/soap+xml'
                typecode = 'AR' if len(errors) > 0 else 'AA'
                subRef = ''
                if mongoId is not None:
                    subEndpoint = 'http://%s:%s/subscription/%s' % (MYIP, worker_port-1, str(mongoId))
                    subRef = '''
                    <wsnt:SubscriptionReference xmlns:wsnt="%s">
                    <wsa:Address xmlns:wsa="%s">%s</wsa:Address>
                    </wsnt:SubscriptionReference>''' % (NS['wsnt'], NS['wsa'], subEndpoint)
                ackDetail = ''
                if len(errors)>0:
                    print errors[0]
                    ackDetail = """
                        <acknowledgementDetail typeCode='E'>
                          <code code='%(code)s' displayName=' ' codeSystem='2.16.840.1.113883.5.1100'
                                codeSystemName='AcknowledgementDetailCode'/>
                          <text>%(text)s</text>
                          <location></location>
                        </acknowledgementDetail>""" % errors[0]
                ts = time.strftime('%Y%m%d%H%M%S',time.gmtime())
                ackId = uuid.uuid4().hex
                return ["""<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope'>
 <s:Header>
  %s
 </s:Header>
 <s:Body>
    <MCCI_IN000002UV01 ITSVersion='XML_1.0' xmlns='urn:hl7-org:v3'>
	<id root='' extension='%s'/>
	<creationTime value='%s'/>
        <interactionId extension='MCCI_IN000002UV01' root='2.16.840.1.113883.5'/>
        <processingModeCode code='T'/> <!-- T means current processing -->
	<acceptAckCode code='NE'/>
	<receiver typeCode='RCV'>
		<device classCode='DEV' determinerCode='INSTANCE'>
			<id/>
		</device>
	</receiver>
	<sender typeCode='RCV'>
		<device classCode='DEV' determinerCode='INSTANCE'>
			<id/>
		</device>
	</sender>
        <acknowledgement typeCode='%s'>
          %s
        </acknowledgement>
   </MCCI_IN000002UV01>
</s:Body></s:Envelope>""" % (subRef, ackId, ts, typecode, ackDetail)]

class DocsHandler:
        exposed = True
        def __init__(self, mongoHost):
                self.con = pymongo.Connection(host=mongoHost)
        def GET(self, docid=None, cnt = None):
                max = int(cnt) if cnt else 50
                try:
                        if not docid:
                                crs = self.con.xds.docs.find(fields=['entryUUID','patientId'],
                                                             sort=[('storedAt_', pymongo.DESCENDING)],
                                                             limit=max)
                                lis = "\n".join(["<li><a href='./%s'>%s</a> (patient:'<b>%s</b>')</li>"
                                                 % (d['entryUUID'],d['entryUUID'], d.get('patientId', '') )
                                                 for d in crs])
                                return """<html><head><title>XDS repository: docs recently submitted</title></head>
                                <body><h1>The last %s docs submitted</h1>
                                <ul>%s</ul>
                                </body>
                                </html>""" % (max, lis)
                        else:
                                d = self.con.xds.docs.find_one({'entryUUID':docid})
                                if not d:
                                        cherrypy.notfound()
                                from pymongo import json_util
                                s = json.dumps(d, default=json_util.default, sort_keys=True, indent = 4)
                                return """<html><head><title>XDS repository: docs recently submitted</title></head>
                                <body><h1>Document %s</h1>
                                <p><a href='%s'>contents</a> (%s)</p>
                                <h3>Document metadata (raw)</h3>
                                <pre>%s</pre>
                                </body>
                                </html>""" % (d['entryUUID'], d['URI'], d.get('mimeType', ''), s)
                except Exception, ex:
                        print "ERROR: %s" % (ex)
                        raise cherrypy.HTTPError()
                finally:
                        self.con.end_request()
                                
def send_notification(port, type, sub):
    from socket import socket, AF_INET,SOCK_STREAM
    msg = {'type':type, 'payload': sub}
    data = bson.BSON.encode(msg)
    addr = ('localhost', port)
    sock = socket(AF_INET, SOCK_STREAM)
    try:
        sock.connect(addr)
        sock.send(data)
    except Exception, ex:
        print "ERROR (send notification): %s" % ex
    finally:
        sock.close()

# See Avoiding TCP/IP Port exhaustion in Windows
# http://goo.gl/E1xsa
def send_subscription_notification(sub):
        workers = cherrypy.config['icardea_interop'].notify_ports
        w = random.choice(workers)
        print 'pushing subscription to ', w 
        send_notification(w, 'subscription', sub)
        return w
        
def send_submission_notification(sset):
        workers = cherrypy.config['icardea_interop'].notify_ports
        for w in workers:
                print 'pushing sset to ', w 
                send_notification(w, 'submission', sset)
class EHRInteropApp:
        exposed = True
        def __init__(self, options):
                self.options = options
        def GET(self):
                headers = cherrypy.request.headers
                myhost = socket.gethostbyname(socket.getfqdn())
                base = cherrypy.request.base
                if headers.has_key('X-Forwarded-Host'):
                        host = headers['X-Forwarded-Host']
                        proto = 'https' if headers.has_key('X-Forwarded-Ssl') else 'http'
                        base = proto +'://' + host + '/icardea'
                wor_base = cherrypy.request.scheme +'://' + myhost
                hs = ', '.join("<a href='%s:%s/'>worker %s</a>" % (wor_base, w-1, i+1)
                               for i, w in enumerate(self.options.notify_ports))
                return ["""<html>
 <head><title>iCARDEA EHR interoperability Framework </title></head>
 <body>
 <h1>iCARDEA EHR interoperability Framework</h1>
 We offer the following services:
 <ul>

 <li><a href="xds/">%s/xds/</a>: Here you POST your
 <a href='http://wiki.ihe.net/index.php?title=XDS.b'>XDS.b</a> messages. We implement
 both the XDS Registry and Repository functionality</li>
 
 <li><a href="pcc/">%s/pcc/</a>: Here you POST your
 <a href='http://wiki.ihe.net/index.php?title=PCC-9'>PCC-9</a> messages to subscribe
 to a patients clinical data updates.</li>

 </ul>
 <p> Also for debugging purposes you can see:
 <ul><li>The current PCC-CM "subscriptions": %s</li>
 <li>The
 <a href='docs/'>the most recent documents submitted</a></li>
 <li>The
 <a href='xdsdb/'>whole XDS database as stored in the filesystem</a></li>
 </ul>

 &copy; 2010-2011 FORTH-ICS All rights reserved.
 </body></html>""" % (base, base, hs)]

# cherrypy needs an absolute path when dealing wwith static data
current_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
print "curdir=%s" % current_dir

conf = {
        '/': {
                'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
                'tools.staticdir.root': current_dir
        },
        '/xdsdocs': {
                'tools.staticdir.on' : True,
                'tools.staticdir.root': current_dir,
                'tools.staticdir.dir' : 'static'
        },
        '/xdsref': {
                'tools.staticdir.on' : True,
                'tools.staticdir.root':  os.path.join(current_dir, "static"),
                'tools.staticdir.dir' : 'xdsref'
        }
}


def _process_request_body_hook():
        cherrypy.request.process_request_body = False

cherrypy.request.hooks.attach('before_request_body', _process_request_body_hook)
#app = cherrypy.tree.mount(EHRInteropApp(), '/', config=conf)
def parse_options():
    parser = OptionParser(usage = "usage: %prog [options]")
    parser.set_defaults(port = XDS_LISTEN_PORT, mongohost = MONGO_HOST, notify_ports=[])
    parser.add_option("-p", "--port", action="store", dest="port", type="int",
                      help='The TCP port for the XDS server to use. Default: %s'% XDS_LISTEN_PORT)
    parser.add_option("-m", "--mongohost", action="store", dest="mongohost", type="string",
                      help='The hostname/IP address of MongoDB. Default: %s'% MONGO_HOST )
    parser.add_option("-n", action="append", dest="notify_ports", type="int",
                      help='The TCP port that the UB listens to. Use 0 to deactivate. Multiple values allowed.Default: %s'% UB_LISTEN_PORT)
    (options, args) = parser.parse_args()
    if len(options.notify_ports) == 0:
            options.notify_ports = [UB_NOTIFY_PORT]
    elif options.notify_ports[0] == 0:
            options.notify_ports = []
    return options

if __name__ == "__main__":
        options = parse_options()
        cherrypy.config.update({'global':{
                'server.socket_port': options.port,
                'server.socket_host': '0.0.0.0',
                'engine.autoreload_on' : True,
                'log.screen': True
                }})
        cherrypy.config.update({'icardea_interop': options})
        root = EHRInteropApp(options)
        root.pcc = PCC9_Handler(options.mongohost)
        root.xds = XDS_Handler(options.mongohost)
        root.docs = DocsHandler(options.mongohost)
        print "Listening on %s .. sending notifications in %s" % (options.port,
                                                                  ','.join(str(w) for w in options.notify_ports))
        cherrypy.quickstart(root, '/', config=conf)
