#!/usr/bin/env python3

import yaml
import argparse
import logging
import pprint
from vbincarver.parser import FileParser
from vbincarver.formatter import HexFormatter, SummaryFormatter
from vbincarver.config import FormatConfig

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument( '-f', '--format', action='store', required=True,
        help='Path to the formatting YAML grammar file.' )

    parser.add_argument(
        '-o', '--out-file', action='store', default='output.html',
        help='Path to the HTML output file to create.' )

    mutex_verbose = parser.add_mutually_exclusive_group()
    
    mutex_verbose.add_argument( '-v', '--verbose', action='store_true' )

    mutex_verbose.add_argument(
        '-vv', '--extra-verbose', action='store_true' )

    parser.add_argument( 'parse_file', action='store',
        help='Path to the file to dissect.' )

    args = parser.parse_args()

    log_level = logging.INFO
    if args.verbose or args.extra_verbose:
        log_level = logging.DEBUG
    logging.basicConfig( level=log_level )
    logger = logging.getLogger( 'main' )

    if not args.extra_verbose:
        storage_logger = logging.getLogger( 'storage' )
        storage_logger.setLevel( level=logging.INFO )

        chunk_logger = logging.getLogger( 'chunk' )
        chunk_logger.setLevel( level=logging.INFO )

        parser_logger = logging.getLogger( 'parser.parse.byte' )
        parser_logger.setLevel( level=logging.INFO )

        parser_logger = logging.getLogger( 'parser.add' )
        parser_logger.setLevel( level=logging.INFO )

        parser_logger = logging.getLogger( 'parser.select' )
        parser_logger.setLevel( level=logging.INFO )

        parser_logger = logging.getLogger( 'parser.repeats' )
        parser_logger.setLevel( level=logging.INFO )

    logger.debug( 'starting...' )

    format_data = FormatConfig( args.format )

    with open( args.out_file, 'w' ) as out_file:
        with open( args.parse_file, 'rb' ) as parse_file:
            file_parser = FileParser( parse_file.read(), format_data )

            file_parser.parse()
            formatter = HexFormatter( out_file, file_parser )
            formatter.write_header()
            formatter.write_layout()
            formatter.write_footer()

            #printer = pprint.PrettyPrinter()
            #printer.pprint( file_parser.buffer )

            formatter = SummaryFormatter( out_file, file_parser )
            formatter.write_layout()

            out_file.write( '</body></html>' )

if '__main__' == __name__:
    main()

