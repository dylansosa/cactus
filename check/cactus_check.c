#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <getopt.h>

#include "cactus.h"
#include "commonC.h"

/*
 * The script checks the nets are structured as we expect, essentially by
 * calling net_check for each net in the tree. We do a couple of other tests also..
 */

static void checkBasesAccountedFor(Net *net) {
	int64_t totalBases = net_getTotalBaseLength(net);
	int64_t blockBases = 0.0;
	int64_t childBases = 0.0;
	Net_BlockIterator *blockIterator = net_getBlockIterator(net);
	Block *block;
	Block_InstanceIterator *segmentIterator;
	Segment *segment;
	while((block = net_getNextBlock(blockIterator)) != NULL) {
		segmentIterator = block_getInstanceIterator(block);
		while((segment = block_getNext(segmentIterator)) != NULL) {
			if(segment_getSequence(segment) != NULL) {
				blockBases += segment_getLength(segment);
			}
		}
		block_destructInstanceIterator(segmentIterator);
	}
	net_destructBlockIterator(blockIterator);
	Net_GroupIterator *iterator = net_getGroupIterator(net);
	Group *group;
	while((group = net_getNextGroup(iterator)) != NULL) {
		int64_t size = (int64_t)group_getTotalBaseLength(group);
		if(group_getNestedNet(group) != NULL) {
			assert(!group_isTerminal(group));
			assert(net_getTotalBaseLength(group_getNestedNet(group)) == size);
		}
		else {
			assert(group_isTerminal(group));
		}
		assert(size >= 0);
		childBases += size;
	}
	net_destructGroupIterator(iterator);
	if(blockBases + childBases != totalBases) {
		fprintf(stderr, "Got %i block bases, %i childBases and %i total bases\n", (int)blockBases, (int)childBases, (int)totalBases);
	}
	assert(blockBases + childBases == totalBases);
}

static void checkNets(Net *net, int32_t recursive) {
	net_check(net);
	checkBasesAccountedFor(net);
	//Call problem recursively
	if(recursive) {
		Net_GroupIterator *iterator = net_getGroupIterator(net);
		Group *group;
		while((group = net_getNextGroup(iterator)) != NULL) {
			if(!group_isTerminal(group)) {
				checkNets(group_getNestedNet(group), 1);
			}
		}
		net_destructGroupIterator(iterator);
	}
}

void usage() {
	fprintf(stderr, "cactus_tree, version 0.2\n");
	fprintf(stderr, "-a --logLevel : Set the log level\n");
	fprintf(stderr, "-c --netDisk : The location of the net disk directory\n");
	fprintf(stderr, "-e --recursive : Check all nets recursively\n");
	fprintf(stderr, "-h --help : Print this help screen\n");
}

int main(int argc, char *argv[]) {
	NetDisk *netDisk;
	Net *net;

	/*
	 * Arguments/options
	 */
	char * logLevelString = NULL;
	char * netDiskName = NULL;
	int32_t recursive = 0;

	///////////////////////////////////////////////////////////////////////////
	// (0) Parse the inputs handed by genomeCactus.py / setup stuff.
	///////////////////////////////////////////////////////////////////////////

	while(1) {
		static struct option long_options[] = {
			{ "logLevel", required_argument, 0, 'a' },
			{ "netDisk", required_argument, 0, 'c' },
			{ "recursive", no_argument, 0, 'e' },
			{ "help", no_argument, 0, 'h' },
			{ 0, 0, 0, 0 }
		};

		int option_index = 0;

		int key = getopt_long(argc, argv, "a:c:eh", long_options, &option_index);

		if(key == -1) {
			break;
		}

		switch(key) {
			case 'a':
				logLevelString = stringCopy(optarg);
				break;
			case 'c':
				netDiskName = stringCopy(optarg);
				break;
			case 'e':
				recursive = 1;
				break;
			case 'h':
				usage();
				return 0;
			default:
				usage();
				return 1;
		}
	}

	///////////////////////////////////////////////////////////////////////////
	// (0) Check the inputs.
	///////////////////////////////////////////////////////////////////////////

	assert(netDiskName != NULL);

	//////////////////////////////////////////////
	//Set up logging
	//////////////////////////////////////////////

	if(logLevelString != NULL && strcmp(logLevelString, "INFO") == 0) {
		setLogLevel(LOGGING_INFO);
	}
	if(logLevelString != NULL && strcmp(logLevelString, "DEBUG") == 0) {
		setLogLevel(LOGGING_DEBUG);
	}

	//////////////////////////////////////////////
	//Log (some of) the inputs
	//////////////////////////////////////////////

	logInfo("Net disk name : %s\n", netDiskName);

	//////////////////////////////////////////////
	//Load the database
	//////////////////////////////////////////////

	netDisk = netDisk_construct(netDiskName);
	logInfo("Set up the net disk\n");

	int32_t j;
	for (j = optind; j < argc; j++) {
		const char *netName = argv[j];
		logInfo("Processing the net named: %s", netName);

		///////////////////////////////////////////////////////////////////////////
		// Parse the basic reconstruction problem
		///////////////////////////////////////////////////////////////////////////

		net = netDisk_getNet(netDisk, netMisc_stringToName(netName));
		logInfo("Parsed the top level net of the cactus tree to check\n");

		///////////////////////////////////////////////////////////////////////////
		// Recursive check the nets.
		///////////////////////////////////////////////////////////////////////////

		checkNets(net, recursive);
		logInfo("Checked the nets/\n");
	}

	///////////////////////////////////////////////////////////////////////////
	// Clean up.
	///////////////////////////////////////////////////////////////////////////

	netDisk_destruct(netDisk);

	return 0;
}
