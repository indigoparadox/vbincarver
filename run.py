#!/usr/bin/env python3

import yaml
import argparse
import logging
import pprint
from vbincarver.parser import FileParser
from vbincarver.formatter import HexFormatter, SummaryFormatter

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

    format_data = None
    with open( args.format, 'r' ) as format_file:
        format_data = yaml.load( format_file, Loader=yaml.Loader )
        for struct_key in format_data['structs']:
            struct_def = format_data['structs'][struct_key]
            struct_def['counts_written'] = 0
            if 'offset_field' in struct_def:
                struct_def['offset_field'] = \
                    struct_def['offset_field'].split( '/' )
            if 'count_field' in struct_def:
                struct_def['count_field'] = \
                    struct_def['count_field'].split( '/' )

            for field_key in struct_def['fields']:
                field_def = struct_def['fields'][field_key]
                field_def['parent'] = struct_key
                if 'count_field' in field_def:
                    field_def['count_field'] = \
                        field_def['count_field'].split( '/' )
                if 'count_mod' not in field_def:
                    field_def['count_mod'] = \
                        'count_field' # Pass straight thru eval().
                if 'lsbf' not in field_def:
                    field_def['lsbf'] = False
                if 'summarize' not in field_def:
                    field_def['summarize'] = 'default'
                if 'hidden' not in field_def:
                    field_def['hidden'] = False
                if 'format' not in field_def:
                    field_def['format'] = 'number'
                if 'term_style' not in field_def:
                    field_def['term_style'] = 'static'
                if 'match_field' in field_def:
                    field_def['match_field'] = \
                        field_def['match_field'].split( '/' )
                    if 2 > len( field_def['match_field'] ):
                        field_def['match_field'] = \
                            [struct_key, field_def['match_field'][0]]

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

