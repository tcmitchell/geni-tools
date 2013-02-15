#!/usr/bin/env python

#----------------------------------------------------------------------
# Copyright (c) 2013 Raytheon BBN Technologies
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and/or hardware specification (the "Work") to
# deal in the Work without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Work, and to permit persons to whom the Work
# is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Work.
#
# THE WORK IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE WORK OR THE USE OR OTHER DEALINGS
# IN THE WORK.
#----------------------------------------------------------------------
import copy
import datetime
import logging

import omni
from omnilib.util import OmniError, naiveUTC
import omnilib.util.handler_utils as handler_utils
from omnilib.util.files import readFile
import omnilib.util.credparsing as credutils

import omnilib.stitch.scs as scs
import omnilib.stitch.RSpecParser
from omnilib.stitch.workflow import WorkflowParser
import omnilib.stitch as stitch
from omnilib.stitch.utils import StitchingError
from omnilib.stitch.objects import Aggregate

from geni.util.rspec_util import is_rspec_string, is_rspec_of_type, rspeclint_exists, validate_rspec

# The main stitching class. Holds all the state about our attempt at doing stitching.
class StitchingHandler(object):
    '''Workhorse class to do stitching'''

    def __init__(self, opts, config, logger):
        self.logger = logger
        config['logger'] = logger
        self.omni_config = config['omni']
        self.config = config
        self.opts = opts # command line options as parsed
        self.framework = omni.load_framework(self.config, self.opts)

    def doStitching(self, args):
        # Get request RSpec
        request = None
        command = None
        self.slicename = None
        if len(args) > 0:
            command = args[0]
        if not command or command.strip().lower() not in ('createsliver', 'allocate'):
            # Stitcher only handles createsliver or allocate
            if self.opts.fakeModeDir:
                self.logger.info("In fake mode. Otherwise would call Omni with args %r", args)
                return
            else:
                self.logger.info("Passing call to Omni")
                return omni.call(args, self.opts)

        if len(args) > 1:
            self.slicename = args[1]
        if len(args) > 2:
            request = args[2]

        if len(args) > 3:
            self.logger.warn("Arguments %s ignored", args[3:])
        self.logger.info("Command=%s, slice=%s, rspec=%s", command, self.slicename, request)

        # Parse the RSpec
        requestString = ""
        self.rspecParser = omnilib.stitch.RSpecParser.RSpecParser(self.logger)
        self.parsedUserRequest = None
        if request:
            try:
                # read the rspec into a string, and add it to the rspecs dict
                requestString = readFile(request)
            except Exception, exc:
                msg = 'Unable to read rspec file %s: %s' % (request, str(exc))
                raise OmniError(msg)

            #    # Test if the rspec is really json containing an RSpec, and pull out the right thing
            #    requestString = amhandler.self._maybeGetRSpecFromStruct(requestString)

            # confirmGoodRequest
            self.confirmGoodRequest(requestString)
            self.logger.debug("Valid GENI v3 request RSpec")
            
            # parseRequest
            self.parsedUserRequest = self.rspecParser.parse(requestString)
            
        # If this is not a real stitching thing, just let Omni handle this.
        if not self.mustCallSCS(self.parsedUserRequest):
            # Warning: If this is createsliver and you specified multiple aggregates,
            # then omni only contacts 1 aggregate. That is likely not what you wanted.
            return omni.call(args, self.opts)

        # Remove any -a arguments from the opts so that when we later call omni
        # the right thing happens
        self.opts.aggregate = []

        # Ensure the slice is valid before all those Omni calls use it
        sliceurn = self.confirmSliceOK()
    
        self.scsService = scs.Service(self.opts.scsURL)

        scsResponse = self.callSCS(sliceurn, requestString)
#        scsResponse = self.callSCS(sliceurn, self.parsedUserRequest)

        # Parse SCS Response, constructing objects and dependencies, validating return
        parsed_rspec, workflow_parser = self.parseSCSResponse(scsResponse)

        # FIXME: if notScript, print AM dependency tree?

        ams_to_process = copy.copy(workflow_parser.aggs)
        for amURN in parsed_rspec.amURNs:
            found = False
            for agg in ams_to_process:
                if agg.urn == amURN:
                    found = True
                    break
            if found:
                continue
            else:
                self.logger.error("RSpec requires AM %s which is not in workflow", amURN)
                am = Aggregate.find(amURN)
                if not am.url:
                    self.logger.error("And stitcher does not know the URL for that AM!")
                else:
                    ams_to_process.add(am)

        # Do Main loop (below)
        self.mainStitchingLoop(ams_to_process, parsed_rspec)
          # Are all AMs marked reserved/done? Exit main loop
          # Any AMs marked should-delete? Do Delete 1 AM
          # Any AMs have all dependencies satisfied? For each, do Reserve 1 AM

        # FIXME: Do cleanup if any, construct return, return to stitcher.main (see above)
          # Construct a unified manifest
          # include AMs, URLs, API versions
          # use code/value/output struct
          # If error and have an expanded rquest from SCS, include that in output.
          #   Or if particular AM had errors, ID the AMe and errors

        return ""

    def mainStitchingLoop(self, aggs, rspec):

        # Check if done? (see elsewhere)
        # Check threads exited
        # Check for AMs with delete pending
          # Construct omni args
          # Mark delete in process
          # omni.newthread_call
        # Check for threads exited
        # Check for AMs with redo pending
          # FIXME: Is this a thing? Or is this same as reserve?
        # Construct omni args
        # Mark redo in process
        # omni.newthread_call
        # Check for threads exited
        # Check for AMs to reserve, no remaining dependencies
          # Construct omni args
          # Mark reserve in process
          # Omni.newthread_call
        # Any ops in process?
          # Since when op finishes we go to top of loop, and loop spawns things, then if not we must be done
            # Confirm no deletes pending, redoes, or AMs not reserved
            # Go to end state section
        launcher = stitch.Launcher(self.opts, self.slicename, aggs)
        try:
            launcher.launch(rspec)
        except StitchingError, se:
            self.logger.warn("Stitching failed with an error")
            for am in launcher.aggs:
                if am.manifestDom:
                    self.logger.warn("Had reservation at %s", am.url)
                    try:
                        am.deleteReservation(self.opts, self.slicename)
                        self.logger.warn(".... deleted it")
                    except StitchingError, se2:
                        self.logger.warn("Failed to delete reservation at %s: %s", am.url, se2)
            raise se

    def confirmGoodRequest(self, requestString):
        # Confirm the string is a request rspec, valid
        if requestString is None or str(requestString).strip() == '':
            raise OmniError("Empty request rspec")
        if not is_rspec_string(requestString, self.logger):
            raise OmniError("Request RSpec file did not contain an RSpec")
        if not is_rspec_of_type(requestString):
            raise OmniError("Request RSpec file did not contain a request RSpec (wrong type or schema)")
        try:
            rspeclint_exists()
        except:
            self.logger.debug("No rspeclint found")
            return
        if not validate_rspec(requestString):
            raise OmniError("Request RSpec does not validate against its schemas")

    def confirmSliceOK(self):
        # Ensure the given slice name corresponds to a current valid slice

        # Get slice URN from name
        try:
            sliceurn = self.framework.slice_name_to_urn(self.slicename)
        except Exception, e:
            self.logger.error("Could not determine slice URN from name: %s", e)
            raise StitchingError(e)

        if self.opts.fakeModeDir:
            self.logger.info("Fake mode: not checking slice credential")
            return sliceurn

        # Get slice cred
        (slicecred, message) = handler_utils._get_slice_cred(self, sliceurn)
        if not slicecred:
            # FIXME: Maybe if the slice doesn't exist, create it?
            # omniargs = ["createslice", self.slicename]
            # try:
            #     (slicename, message) = omni.call(omniargs, self.opts)
            # except:
            #     pass
            raise StitchingError("Could not get a slice credential for slice %s: %s" % (sliceurn, message))

        # Ensure slice not expired
        sliceexp = credutils.get_cred_exp(self.logger, slicecred)
        sliceexp = naiveUTC(sliceexp)
        now = datetime.datetime.utcnow()
        if sliceexp <= now:
            # FIXME: Maybe if the slice doesn't exist, create it?
            # omniargs = ["createslice", self.slicename]
            # try:
            #     (slicename, message) = omni.call(omniargs, self.opts)
            # except:
            #     pass
            raise StitchingError("Slice %s expired at %s" % (sliceurn, sliceexp))
        
        # return the slice urn
        return sliceurn

    def mustCallSCS(self, requestRSpecObject):
        # Does this request actually require stitching?
        # Check: >=1 link in main body with >= 2 diff component_manager names and no shared_vlan extension
        if requestRSpecObject:
            for link in requestRSpecObject.links:
                # FIXME: hasSharedVlan is not correctly set yet
                if len(link.aggregates) > 1 and not link.hasSharedVlan:
                    return True
        return False

#    def callSCS(self, sliceurn, requestRSpecObject):
    def callSCS(self, sliceurn, requestString):
        try:
 #           request, scsOptions = self.constructSCSArgs(requestRSpecObject)
            request, scsOptions = self.constructSCSArgs(requestString)
            scsResponse = self.scsService.ComputePath(sliceurn, request, scsOptions)
        except Exception as e:
            self.logger.error("Error from slice computation service: %s", e)
            raise StitchingError("SCS gave error: %s" % e)

        self.logger.info("SCS successfully returned.");

        if self.opts.debug:
            self.logger.debug("Writing SCS result JSON to scs-result.json")
            with open ("scs-result.json", 'w') as file:
                file.write(str(self.scsService.result))

        return scsResponse

    def constructSCSArgs(self, request, hopObjectsToExclude=None):
        # Eventually take vlans to exclude as well
        # return requestString and options

        options = {} # No options for now.
        # options is a struct
        # To exclude a hop, add a geni_routing_profile struct
        # This in turn should have a struct per path whose name is the path name
        # Each shuld have a hop_exclusion_list array, containing the names of hops
#        exclude = "urn:publicid:IDN+utah.geniracks.net+interface+procurve2:1.19"
#        path = "link-utah-utah-ig"

#        path = "link-pg-utah1-ig-gpo1"
#        exclude = "urn:publicid:IDN+ion.internet2.edu+interface+rtr.atla:ge-7/1/6:protogeni"
#        excludes = []
#        excludes.append(exclude)
#        exclude = "urn:publicid:IDN+ion.internet2.edu+interface+rtr.hous:ge-9/1/4:protogeni"
#        excludes.append(exclude)
#        exclude = "urn:publicid:IDN+ion.internet2.edu+interface+rtr.losa:ge-7/1/3:protogeni"
#        excludes.append(exclude)
#        exclude = "urn:publicid:IDN+ion.internet2.edu+interface+rtr.salt:ge-7/1/2:*"
##        excludes.append(exclude)
#        exclude = "urn:publicid:IDN+ion.internet2.edu+interface+rtr.wash:ge-7/1/3:protogeni"
#        excludes.append(exclude)
#        profile = {}
#        pathStruct = {}
#        pathStruct["hop_exclusion_list"]=excludes
#        profile[path] = pathStruct
#        options["geni_routing_profile"]=profile

        if hopObjectsToExclude:
            profile = {}
            for hop in hopObjectsToExclude:
                # get path
                path = hop._path.id
                if profile.has_key(path):
                    pathStruct = profile[path]
                else:
                    pathStruct = {}

                # get hop URN
                urn = hop.urn
                if pathStruct.has_key("hop_exclusion_list"):
                    excludes = pathStruct["hop_exclusion_list"]
                else:
                    excludes = []
                excludes.append(urn)
                pathStruct["hop_exclusion_list"] = excludes
                profile[path] = pathStruct
            options["geni_routing_profile"] = profile

#        return request.toXML(), options
        return request, options
        
    def parseSCSResponse(self, scsResponse):
        # save expanded RSpec
        expandedRSpec = scsResponse.rspec()
        if self.opts.debug:
            self.logger.debug("Writing SCS expanded RSpec to expanded.xml")
            with open("expanded.xml", 'w') as file:
                file.write(expandedRSpec)

       # parseRequest
        parsed_rspec = self.rspecParser.parse(expandedRSpec)
        self.logger.debug("Parsed SCS expanded RSpec of type %r",
                          type(parsed_rspec))
        #with open('gen-rspec.xml', 'w') as f:
        #    f.write(parsed_rspec.dom.toxml())

        # parseWorkflow
        workflow = scsResponse.workflow_data()
        if self.opts.debug:
            import pprint
            pp = pprint.PrettyPrinter(indent=2)
            pp.pprint(workflow)

        workflow_parser = WorkflowParser(self.logger)

        # Parse the workflow, creating Path/Hop/etc objects
        # In the process, fill in a tree of which hops depend on which,
        # and which AMs depend on which
        # Also mark each hop with what hop it imports VLANs from,
        # And check for AM dependency loops
        workflow_parser.parse(workflow, parsed_rspec)

        # FIXME: check each AM reachable, and we know the URL/API version to use

        # FIXME: Check SCS output consistency in a subroutine:
          # In each path: An AM with 1 hop must either _have_ dependencies or _be_ a dependency
          # All AMs must be listed in workflow data at least once per path they are in

        # Add extra info about the aggregates to the AM objects
        self.add_am_info(workflow_parser.aggs)

        if self.opts.debug:
            self.dump_objects(parsed_rspec, workflow_parser.aggs)

        return parsed_rspec, workflow_parser

    def add_am_info(self, aggs):
        options_copy = copy.deepcopy(self.opts)
        options_copy.debug = False
        options_copy.info = False

        # Note which AMs were user requested
        for agg in aggs:
            if agg.urn in self.parsedUserRequest.amURNs:
                agg.userRequested = True

# For using the test ION AM
#            if 'alpha.dragon' in agg.url:
#                agg.url =  'http://alpha.dragon.maxgigapop.net:12346/'

            # Query AM API versions supported, then set the max as property on the aggregate
                # then use that to pick allocate vs createsliver
            # Check GetVersion geni_am_type contains 'dcn'. If so, set flag on the agg
            omniargs = ['--ForceUseGetVersionCache', '-o', '--warn', '-a', agg.url, 'getversion']
            try:
                self.logger.info("Getting extra AM info from Omni for AM %s", agg)
                logging.disable(logging.INFO)
                (text, version) = omni.call(omniargs, options_copy)
                logging.disable(logging.NOTSET)
                if isinstance (version, dict) and version.has_key(agg.url) and isinstance(version[agg.url], dict) \
                        and version[agg.url].has_key('value') and isinstance(version[agg.url]['value'], dict):
                    if version[agg.url]['value'].has_key('geni_am_type') and isinstance(version[agg.url]['value']['geni_am_type'], list):
                        if 'dcn' in version[agg.url]['value']['geni_am_type']:
                            self.logger.debug("AM %s is DCN", agg)
                            agg.dcn = True
                    if version[agg.url]['value'].has_key('geni_api_versions') and isinstance(version[agg.url]['value']['geni_api_versions'], dict):
                        maxVer = 1
                        for key in version[agg.url]['value']['geni_api_versions'].keys():
                            if int(key) > maxVer:
                                maxVer = int(key)
                        # Hack alert: v3 AM implementations don't work even if they exist
                        if maxVer != 2:
                            self.logger.info("AM %s speaks API %d, but sticking with v2", agg, maxVer)
#                        agg.api_version = maxVer
            except OmniError, oe:
                logging.disable(logging.NOTSET)

    def dump_objects(self, rspec, aggs):
        '''Print out the hops, aggregates, dependencies'''
        stitching = rspec.stitching
        self.logger.debug( "\n===== Hops =====")
        for path in stitching.paths:
            self.logger.debug( "Path %s" % (path.id))
            for hop in path.hops:
                self.logger.debug( "  Hop %s" % (hop))
                # FIXME: don't use the private variable
                self.logger.debug( "    VLAN Suggested (requested): %s" % (hop._hop_link.vlan_suggested_request))
                self.logger.debug( "    VLAN Available Range (requested): %s" % (hop._hop_link.vlan_range_request))
                self.logger.debug( "    Import VLANs From: %s" % (hop.import_vlans_from))
                deps = hop.dependsOn
                if deps:
                    self.logger.debug( "    Dependencies:")
                    for h in deps:
                        self.logger.debug( "      Hop %s" % (h))


        self.logger.debug( "\n===== Aggregates =====")
        for agg in aggs:
            self.logger.debug( "\nAggregate %s" % (agg))
            if agg.userRequested:
                self.logger.debug("   (User requested)")
            else:
                self.logger.debug("   (SCS added)")
            if agg.dcn:
                self.logger.debug("   A DCN Aggregate")
            self.logger.debug("   Using AM API version %d", agg.api_version)
            for h in agg.hops:
                self.logger.debug( "  Hop %s" % (h))
            for ad in agg.dependsOn:
                self.logger.debug( "  Depends on %s" % (ad))

    def _raise_omni_error( self, msg, err=OmniError, triple=None ):
        msg2 = msg
        if triple is not None:
            msg2 += " "
            msg2 += str(triple)
        self.logger.error( msg2 )
        if triple is None:
            raise err, msg
        else: 
            raise err, (msg, triple)

