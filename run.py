#!/usr/bin/env python3

import yaml
import argparse
import logging
import pprint
from vbincarver.parser import FileParser
from vbincarver.formatter import HexFormatter

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

            storage = file_parser.storage

            out_file.write( '<div class="hex-fields"><div>' )
            last_struct = ''
            for key in storage.byte_storage:
                if storage.byte_storage[key]['struct'] != \
                last_struct or \
                storage.byte_storage[key]['sid'] != \
                last_sid:

                    scls = 'hex-struct-{}'.format(
                        storage.byte_storage[key]['struct'] \
                            .replace( '_', '-' ) )
                    sid = scls + '-' + \
                        str( storage.byte_storage[key]['sid'] )

                    # Start a new struct.
                    out_file.write( '<div class="spacer"></div>' )
                    out_file.write(
                        '</div><div class="hex-struct {} {}">'.format(
                            scls, sid ) )
                    out_file.write(
                        '<h3 class="hex-struct-title">{}</h3>'.format(
                            storage.byte_storage[key]['struct']
                                ) )
                    out_file.write(
                        '<div class="hex-struct-sz">({} bytes)</div>'.format(
    
                        # Sum sizes of all fields in the struct.
                        sum( [storage.byte_storage[x]['size'] \
                            for x in storage.byte_storage \
                                if storage.byte_storage[x]['struct'] == \
                                    storage.byte_storage[key]['struct'] and \
                                storage.byte_storage[x]['sid'] == \
                                    storage.byte_storage[key]['sid']] )

                                ) )

                # Write the field.

                hid = storage.byte_storage[key]['field']\
                    .replace( '_', '-' )
                    
                out_file.write(
                    '<div class="spacer"></div>' + \
                    '<span class="hex-field hex-field-' + \
                    hid + '">'
                    '<span class="hex-label">' + \
                        storage.byte_storage[key]['field'] + \
                        '</span>' + \
                    '<span class="hex-sz">(' + \
                    str( storage.byte_storage[key]['size'] ) + \
                        ' bytes)</span>' + \
                    '<span class="hex-contents">' + \
                    str( storage.byte_storage[key]['value'] ) + \
                        '</span></span>' )

                last_struct = storage.byte_storage[key]['struct']
                last_sid = storage.byte_storage[key]['sid']

            out_file.write( '<div class="spacer"></div></div></div>' )

            out_file.write( '</body></html>' )

if '__main__' == __name__:
    main()

