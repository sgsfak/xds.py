The iCARDEA Interoperability Framework
======================================
Stelios Sfakianakis <ssfak@ics.forth.gr>
v1.0, February 2011

This is the code for the iCARDEA Interoperability Framework aimed at
providing the infrastructure for storing the patients' health record
information extracted from the Hospital Information Systems and the
Personal Health Record systems. It comprises the following components:

 - An XDS combined registry and repository for storing medical
   information in the form of CDA documents or other formats
   (e.g. even images can be stored and indexed)

 - An "Update Broker" (ub) which is responsible for sending
   notifications (PCC-10 messages) for changes in the patients health
   records

 - A PIX/PDQ component for handling patient demographic data and
   patients' ids


Please check the link:INSTALL.html[INSTALL] file for information on
installing and running these components. More information about the
testing of the XDS server can be found in the
link:INSTALL.html[TESTING_XDS] file.
