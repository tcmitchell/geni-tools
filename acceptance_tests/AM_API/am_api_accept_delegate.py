#!/usr/bin/python

#----------------------------------------------------------------------
# Copyright (c) 2011 Raytheon BBN Technologies
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
""" Acceptance tests for AM API v1."""

import datetime
from geni.util import rspec_util 
import unittest
import omni_unittest as ut
from omni_unittest import NotDictAssertionError, NotNoneAssertionError
from omni_unittest import NotXMLAssertionError, NoResourcesAssertionError
from omnilib.util import OmniError, NoSliceCredError
import omni
import os
import pprint
import re
import sys
import time
import tempfile

import am_api_accept as accept

# TODO: TEMPORARILY USING PGv2 because test doesn't work with any of the others
# Works at PLC
PGV2_RSPEC_NAME = "ProtoGENI"
PGV2_RSPEC_NUM = 2
RSPEC_NAME = "GENI"
RSPEC_NUM = 3

# TODO: TEMPORARILY USING PGv2 because test doesn't work with any of the others
AD_NAMESPACE = "http://www.protogeni.net/resources/rspec/2"
AD_SCHEMA = "http://www.protogeni.net/resources/rspec/2/ad.xsd"
#GENI_AD_NAMESPACE = "http://www.geni.net/resources/rspec/3"
#GENI_AD_SCHEMA = "http://www.geni.net/resources/rspec/3/ad.xsd"
REQ_NAMESPACE = "http://www.protogeni.net/resources/rspec/2"
REQ_SCHEMA = "http://www.protogeni.net/resources/rspec/2/request.xsd"
#GENI_REQ_NAMESPACE = "http://www.geni.net/resources/rspec/3"
#GENI_REQ_SCHEMA = "http://www.geni.net/resources/rspec/3/request.xsd"
MANIFEST_NAMESPACE = "http://www.protogeni.net/resources/rspec/2"
MANIFEST_SCHEMA = "http://www.protogeni.net/resources/rspec/2/manifest.xsd"
#GENI_MANIFEST_NAMESPACE = "http://www.geni.net/resources/rspec/3"
#GENI_MANIFEST_SCHEMA = "http://www.geni.net/resources/rspec/3/manifest.xsd"

TMP_DIR="."
REQ_RSPEC_FILE="request.xml"
BAD_RSPEC_FILE="bad.xml"
SLEEP_TIME=3
################################################################################
#
# Test AM API v1 calls for accurate and complete functionality.
#
# This script relies on the unittest module.
#
# To run test:
# ./am_api_accept.py -a <AM to test> DelegateTest.test_ListResources_delegatedSliceCred
#
# To add a new test:
# Create a new method with a name starting with 'test_".  It will
# automatically be run when am_api_accept.py is called.
#
################################################################################

# This is the acceptance test for AM API version 1
API_VERSION = 1


class DelegateTest(accept.Test):
    """Delegation acceptance test for GENI AM API v1."""

    def setUp( self ):
        accept.Test.setUp( self )
    def test_ListResources_delegatedSliceCred(self):
        """test_ListResources_delegatedSliceCred: Passes if 'ListResources' succeeds with a delegated slice credential. Override the default slice credential using --delegated-slicecredfile"""
        # Check if slice credential is delegated.
        xml = self.file_to_string( self.options_copy.delegated_slicecredfile )
        self.assertTrue( self.is_delegated_cred(xml), 
                       "Slice credential is not delegated " \
                       "but expected to be. " )
        slice_name = self.get_slice_name_from_cred( xml )                
        self.assertTrue( slice_name,
                       "Credential is not a slice credential " \
                       "but expected to be: \n%s\n\n<snip> " % xml[:100] )
        # Run slice credential
        self.subtest_ListResources(
           slicename=slice_name,
           slicecredfile=self.options_copy.delegated_slicecredfile,
           typeOnly=True)
        self.success = True

if __name__ == '__main__':
    usage = "\n      %s -a am-undertest Test.test_ListResources_delegatedSliceCred" \
            "\n      Also try --vv" % sys.argv[0]
    DelegateTest.accept_parser(usage=usage)
    # Invoke unit tests as usual
    unittest.main()


