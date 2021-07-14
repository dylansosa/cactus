#!/usr/bin/env python3
"""Cut prefixes or suffixes from fasta headeres
"""


import os
import re
import sys
import shutil

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

from cactus.shared.common import RoundedJob
from cactus.shared.common import cactus_call
from toil.realtimeLogger import RealtimeLogger
from cactus.shared.common import getOptionalAttrib, catFiles
from toil.job import Job

class CutHeadersJob(RoundedJob):
    def __init__(self, fastaID, cutBefore, cutBeforeOcc, cutAfter):
        disk = 2*(fastaID.size)
        RoundedJob.__init__(self, disk=disk, preemptable=True)
        self.fastaID = fastaID
        self.cutBefore = cutBefore
        self.cutBeforeOcc = cutBeforeOcc
        self.cutAfter = cutAfter

    def run(self, fileStore):
        """
        Cut before cutBefore and after cutAfter
        
        If cutBefore is # then something like
        >HG02055#1#h1tg000001l
        would become 
        >h1tg000001l

        If cutBeforeOcc is specified, it will only cut up to cutBeforeOcc characters
        so cutBefore # with cutBeforeOcc = 2 would change
        >HG02055#1#h1tg000001l#EBV
        into
        >h1tg000001l#EBV

        If cutAfter is a whitespace, then something like 
        >chr1  AC:CM000663.2  gi:568336023  LN:248956422  rl:Chromosome  M5:6aef897c3d6ff0c78aff06
        would become
        >chr1

        """
        work_dir = fileStore.getLocalTempDir()
        input_path = os.path.join(work_dir, 'seq.fa')
        fileStore.readGlobalFile(self.fastaID, input_path)
        output_path = os.path.join(work_dir, 'seq.cut.fa')

        with open(input_path, 'r') as in_file, open(output_path, 'w') as out_file:
            for seq_record in SeqIO.parse(in_file, 'fasta'):
                header = cut_header(seq_record.description, self.cutBefore, self.cutBeforeOcc, self.cutAfter)
                seq_record.description = header
                seq_record.id = header
                SeqIO.write(seq_record, out_file, 'fasta')

        return fileStore.writeGlobalFile(output_path)

def cut_header(header, cutBefore, cutBeforeOcc, cutAfter):
    if cutBefore:
        occs = [i for i, c in enumerate(header) if c in cutBefore]
        if occs:
            if not cutBeforeOcc:
                pos = occs[-1]
            else:
                pos = occs[min(len(occs), cutBeforeOcc) - 1]
            if pos >= 0:
                if pos < len(header) - 1:
                    header = header[pos + 1:]
                else:
                    header = ""
    if cutAfter:
        pos_list = [header.find(c) for c in cutAfter if header.find(c) >= 0]
        if pos_list:
            pos = min(pos_list)
            header = header[0:pos]

    if not header:
        raise RuntimeError("Error: applying cutHeaders preprocessor removes entire header: {}".format(seq_record.description))

    return header

def make_cut_header_table(job, input_fa_ids, config_node, event_names):
    """
    make a table of <fasta contig name> <cut contig name> <event> <length> for each fasta contig
    this is a dirty hack, but required to properly parse the minigraph GFA
    todo: would be best if this happened during the normal preprocessor, but that requires
    a (much needed) interface cleanup
    why? It's because we get names like CHM13#chr1 in the fastas, and need to change them
    into something browser friendly.  the cutHeaders preprocessor will change it into chr1
    which is fine, but then we lose the link in the minigraph GFA which uses the original 
    contig names.  So the same transformation needs to be applied to both the GFA and fastas,
    which is why we need the preprocessor to keep track of every header it cuts in this table.
    """

    work_dir = job.fileStore.getLocalTempDir()

    prep_nodes = config_node.findall('preprocessor')
    cut_before, cut_before_occ, cut_after = None, None, None
    for prep_node in prep_nodes:
        prep_job_name = getOptionalAttrib(prep_node, 'preprocessJob')
        if prep_job_name == 'cutHeaders' and getOptionalAttrib(prep_node, 'active', typeFn=bool):
            cut_before = getOptionalAttrib(prep_node, 'cutBefore', typeFn=str, default=None)
            cut_before_occ = getOptionalAttrib(prep_node, 'cutBeforeOcc', typeFn=int, default=None)
            cut_after = getOptionalAttrib(prep_node, 'cutAfter', typeFn=str, default=None)

    header_table_ids = []
    root_job = Job()
    job.addChild(root_job)
    for fa_id, event in zip(input_fa_ids, event_names):
        header_job = root_job.addChildJobFn(make_one_header_table, fa_id, event, cut_before, cut_before_occ, cut_after,
                                            disk=fa_id.size)
        header_table_ids.append(header_job.rv())
    join_job = job.addFollowOnJobFn(join_header_table, header_table_ids)

    return join_job.rv()

def make_one_header_table(job, fa_id, event, cut_before, cut_before_occ, cut_after):
    fa_path = job.fileStore.readGlobalFile(fa_id)
    table_path = job.fileStore.getLocalTempFile()
    with open(fa_path, 'r') as fa_file, open(table_path, 'w') as table_file:
        for seq_record in SeqIO.parse(fa_file, 'fasta'):
            header = seq_record.description
            if cut_before or cut_after:
                header = cut_header(seq_record.description, cut_before, cut_before_occ, cut_after)
            table_file.write('{}\t{}\t{}\t{}\n'.format(seq_record.description, header, event, len(seq_record.seq)))
    return job.fileStore.writeGlobalFile(table_path)

def join_header_table(job, header_table_ids):
    header_table_paths = [job.fileStore.readGlobalFile(x) for x in header_table_ids]
    table_path = job.fileStore.getLocalTempFile()
    catFiles(header_table_paths, table_path)
    contig_set = set()
    # do a quick uniqueness check
    with open(table_path, 'r') as table_file:
        for line in table_file:
            toks = line.rstrip().split('\t')
            if toks:
                if toks[0] in contig_set:
                    raise RuntimeError("Error: fasta header {} found in more than one sample.  Headers must be unique to make table".format(toks[0]))
                contig_set.add(toks[0])

    return job.fileStore.writeGlobalFile(table_path)
    
        

    
