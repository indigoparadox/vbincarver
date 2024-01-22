#!/usr/bin/env python3

import yaml
import argparse
import logging
import pprint

COLUMN_LEN = 20

class FileParserStorage( object ):

    def __init__( self ):
        self.field_storage = {}
        self.byte_storage = {}

    def has_struct( self, key : str ):
        return key in self

    def get_field( self, key : tuple ):
        try:
            return self.field_storage[key[0]]['fields'][key[1]]
        except:
            return -1

    def store_field( self, struct_key : str, field_key : str, val : int ):
        logger = logging.getLogger( 'storage.store' )
        logger.debug( 'storing field %s/%s value %d...',
            struct_key, field_key, val )
        if struct_key in self.field_storage:
            if field_key in self.field_storage[struct_key]['fields']:
                self.field_storage[struct_key]['fields'][field_key].append(
                    val )
            else:
                self.field_storage[struct_key]['fields'][field_key] = [val]
        else:
            self.field_storage[struct_key] = {'fields': {field_key: [val]}}

    def store_offset(
        self, offset : int, struct : str, field : str, val : int, sid: int
    ):
        self.byte_storage[offset] = \
            {'struct': struct, 'sid': sid, 'field': field, 'value': val}

class FileParser( object ):

    def __init__( self, in_file, out_file, format_data : dict ):

        self.bytes_written = 0
        self.last_struct = ''
        self.spans_open = []
        self.out_file = out_file
        self.in_file = in_file
        self.format_data = format_data
        self.storage = FileParserStorage()

    def write_header( self ):

        self.out_file.write( '<div class="hex-layout">' )

    def _add_span( self, type_in : str, class_in : str ):
        logger = logging.getLogger( 'parser.add_span' )
        logger.debug( 'adding span for %s: %s',
            type_in, class_in )
        span = {
            'class': class_in,
            'type': type_in,
            'bytes_written': 0
        }
        self.spans_open.append( span )
        self.format_span( span )
        return span

    def add_span_struct( self, class_in : str, fields : dict ):
        for span in self.spans_open:
            assert( 'struct' != span['class'] )
        self.last_struct = class_in
        span = self._add_span( 'struct', class_in )
        span['fields'] = dict( fields ) # Copy!

    def add_span_field( self, class_in : str, **kwargs ):
        
        # Grab the parent struct class.
        assert( 'struct' == self.spans_open[-1]['type'] )
        struct_class = self.spans_open[-1]['class']

        span = self._add_span( 'field', class_in )
        # TODO: String spans?
        span['contents'] = 0
        span['parent'] = struct_class
        span['size'] = kwargs['size']
        span['counts_written'] = 0
        if 'lsbf' in kwargs:
            span['lsbf'] = kwargs['lsbf']
        if 'count_field' in kwargs:
            span['count_field'] = kwargs['count_field'].split( '/' )
        if 'count_mod' in kwargs:
            span['count_mod'] = kwargs['count_mod']
        else:
            span['count_mod'] = 0
        if 'summarize' in kwargs:
            span['summarize'] = kwargs['summarize']
        else:
            span['summarize'] = True

    def span_key( self, span : dict ):

        ''' Return the full heirarchal path to the given span. '''

        return '{}/{}'.format( span['parent'], span['class'] ) \
            if 'field' == span['type'] else span['class']

    def _pop_span( self, idx : int = -1 ):

        ''' Actually remove a span from the list of open spans. Close its
        parent, too, if it was the last child. '''

        logger = logging.getLogger( 'parser.pop_span' )

        span_key = self.span_key( self.spans_open[idx] )

        logger.debug( 'closing span: %s after %d bytes',
            span_key, self.spans_open[idx]['bytes_written'] )

        # Actually remove the span.
        self.spans_open.pop( idx )

        if self.spans_open and \
        'fields' in self.spans_open[-1] and \
        not self.spans_open[-1]['fields']:
            # Parent struct has no more fields. Close the parent
            # struct.
            self.close_span( -1 )

    def close_span( self, idx: int ):
    
        ''' Close or repeat a span as the rules dictate. '''

        logger = logging.getLogger( 'parser.close_span' )

        # Some convenience handlers.
        span = self.spans_open[idx]
        span_key = self.span_key( span )

        if 'struct' == span['type']:
            self.format_data['structs'][span['class']]['counts_written'] += 1

        # Write the closing span and pop the span off the open list.
        self.out_file.write( '</span>' )

        if 'field' == span['type']:
            # Store field contents for later if requested.
            self.storage.store_field(
                span['parent'], span['class'], span['contents'] )

            if 'count_field' in span and \
            self.storage.get_field( span['count_field'] )[-1] \
            + span['count_mod'] > \
            span['counts_written'] + 1:
                # If this is a field, update counts written and restart
                # if the field says we have some left.

                logger.debug( 'repeating span %s (%d/%d)...',
                    span['class'],
                    span['counts_written'],
                    self.storage.get_field(
                        span['count_field'] )[-1] )

                # Refurbish the span to be repeated again.
                self.format_span( span )
                span['contents'] = 0
                span['bytes_written'] = 0
                span['counts_written'] += 1
        
            else:
                self._pop_span()

        else:
            self._pop_span()

    def format_span( self, span : dict ):

        sid = ''
        if 'struct' == span['type']:
            sid = ' hex-struct-' + span['class'].replace( '_', '-' ) \
            + '-' + str(
                self.format_data['structs'][span['class']]['counts_written'] )

        self.out_file.write( '<span class="hex-{} hex-{}-{}{}">'.format(
            span['type'], span['type'],
            span['class'].replace( '_', '-' ),
            sid ) )

    def break_line( self ):

        for span in self.spans_open:
            self.out_file.write( '</span>' )
        self.out_file.write( '</div><div class="hex-line">' )
        for span in self.spans_open:
            self.format_span( span )

    def select_span_struct( self ):

        logger = logging.getLogger( 'parser.select_span.struct' )

        # We're not inside a struct... So find one!
        for key in self.format_data['structs']:
            struct = self.format_data['structs'][key]

            # Figure out if a new struct is starting.

            # Struct that starts at a static field.
            if 'static' == struct['offset_type'] and \
            self.bytes_written == struct['offset']:
                logger.debug( 'found static struct %s at offset: %d',
                    key, self.bytes_written )
                self.add_span_struct( key, struct['fields'] )
                break

            # Struct that repeats based on contents of other field.
            elif self.last_struct == key and \
            'count_field' in struct and \
            self.storage.get_field( struct['count_field'] )[-1] > \
            struct['counts_written']:
                logger.debug( 'struct %s repeats %d more times',
                    key,
                    self.storage.get_field(
                    struct['count_field'] )[-1] - struct['counts_written'] )
                self.add_span_struct( key, struct['fields'] )

            # Struct that starts after a certain other ends.
            elif 'follow' == struct['offset_type'] and \
            self.last_struct == struct['follows']:
                logger.debug( 'struct %s follows struct %s',
                    key, self.last_struct )
                self.add_span_struct( key, struct['fields'] )
                break

            # Struct that starts at a field mentioned elsewhere in the
            # file.
            elif 'offset_field' in struct and \
            [x for x in self.storage.get_field(
            struct['offset_field'] ) if x == self.bytes_written]:
                logger.debug( 'struct %s starts at stored field: %d',
                    key, self.storage.get_field(
                    struct['offset_field'] )[0] )
                self.add_span_struct( key, struct['fields'] )
                break

    def select_span_field( self, open_struct : dict ):
        
        logger = logging.getLogger( 'parser.select_span.field' )

        assert( 'struct' == open_struct['type'] )

        for key in open_struct['fields']:
            field = open_struct['fields'][key]
            if open_struct['bytes_written'] == field['offset']:
                self.add_span_field( key, **field )
                logger.debug( 'removing used field: %s', key )

                # Remove field now that we've written it.
                del open_struct['fields'][key]
                break

    def format_byte( self, byte_in : int ):

        logger = logging.getLogger( 'parser.format_byte' )

        # Add our byte to the open field contents if there is one.
        if self.spans_open and 'field' == self.spans_open[-1]['type']:
            if 'lsbf' in self.spans_open[-1] and self.spans_open[-1]['lsbf']:
                # Shift byte before adding it.
                self.spans_open[-1]['contents'] |= \
                    (byte_in << self.spans_open[-1]['bytes_written'] * 8)
            else:
                self.spans_open[-1]['contents'] <<= 8
                self.spans_open[-1]['contents'] |= byte_in
            #logger.debug( 'current field %s/%s contents: 0x%08x',
            #    self.spans_open[-1]['parent'], self.spans_open[-1]['class'],
            #    self.spans_open[-1]['contents'] )

        # Write our byte.
        self.out_file.write(
            '<span class="{}">{}</span>'.format(
                'byte' if self.spans_open else 'byte_free',
                hex( byte_in ).lstrip( '0x' ).zfill( 2 ) ) )

        # Update accounting.
        self.bytes_written += 1
        for idx in range( len( self.spans_open ) - 1, -1, -1 ):
            self.spans_open[idx]['bytes_written'] += 1

    def parse( self ):

        logger = logging.getLogger( 'parser.parse' )
    
        self.write_header()
        self.out_file.write( '<div class="hex-line">' )
        for file_byte in self.in_file:
            # Break up lines.
            if 0 == self.bytes_written % COLUMN_LEN and \
            0 != self.bytes_written:
                self.break_line()

            if not self.spans_open:
                self.select_span_struct()

            # Not an elif, as it can run after a new struct is added earlier
            # in this method.
            if self.spans_open and 'struct' == self.spans_open[-1]['type']:
                # We're inside a struct but not a field... so find one!
                self.select_span_field( self.spans_open[-1] )
        
            self.format_byte( file_byte )
           
            # Start from the end of the open spans so we don't alter
            # the size of the list while working on it.
            for idx in range( len( self.spans_open ) - 1, -1, -1 ):
                if 'field' == self.spans_open[idx]['type'] and \
                self.spans_open[idx]['bytes_written'] >= \
                self.spans_open[idx]['size']:

                    if self.spans_open[idx]['summarize']:
                        self.storage.store_offset(
                            self.bytes_written - self.spans_open[idx]['size'],
                            self.spans_open[-2]['class'] \
                                if len( self.spans_open ) > 1 else None,
                            self.spans_open[idx]['class'],
                            self.spans_open[idx]['contents'],
                            self.format_data\
                                ['structs'][self.spans_open[idx]['parent']]\
                                ['counts_written'] )

                    self.close_span( idx )
                    if not self.spans_open:
                        # We must've popped the parent struct, too!
                        break

        self.out_file.write( '</div></div>' )

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument( '-f', '--format', action='store', required=True,
        help='Path to the formatting YAML grammar file.' )

    parser.add_argument(
        '-o', '--out-file', action='store', default='output.html',
        help='Path to the HTML output file to create.' )

    parser.add_argument( 'parse_file', action='store',
        help='Path to the file to dissect.' )

    args = parser.parse_args()

    logger = logging.basicConfig( level=logging.DEBUG )

    format_data = None
    with open( args.format, 'r' ) as format_file:
        format_data = yaml.load( format_file, Loader=yaml.Loader )
        for key in format_data['structs']:
            format_data['structs'][key]['counts_written'] = 0
            if 'offset_field' in format_data['structs'][key]:
                format_data['structs'][key]['offset_field'] = \
                    format_data['structs'][key]['offset_field'].split( '/' )
            if 'count_field' in format_data['structs'][key]:
                format_data['structs'][key]['count_field'] = \
                    format_data['structs'][key]['count_field'].split( '/' )

    with open( args.out_file, 'w' ) as out_file:
        with open( args.parse_file, 'rb' ) as parse_file:
            file_parser = FileParser(
                parse_file.read(), out_file, format_data )

            out_file.write( '<!DOCTYPE html><html><head>' )
            out_file.write( '<link rel="stylesheet" href="hex.css" />' )
            out_file.write( '<script src="https://code.jquery.com/jquery-3.7.1.min.js" integrity="sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo=" crossorigin="anonymous"></script>' )
            out_file.write( '<script src="hex.js"></script>' )
            out_file.write( '</head><body>' )

            file_parser.parse()

            printer = pprint.PrettyPrinter()
            printer.pprint( file_parser.storage.byte_storage )

            out_file.write( '<div class="hex-fields"><div>' )
            last_struct = ''
            for key in file_parser.storage.byte_storage:
                if file_parser.storage.byte_storage[key]['struct'] != \
                last_struct or \
                file_parser.storage.byte_storage[key]['sid'] != \
                last_sid:

                    scls = 'hex-struct-{}'.format(
                        file_parser.storage.byte_storage[key]['struct'] \
                            .replace( '_', '-' ) )
                    sid = scls + '-' + \
                        str( file_parser.storage.byte_storage[key]['sid'] )

                    out_file.write( '<div class="spacer"></div>' )
                    out_file.write(
                        '</div><div class="hex-struct {} {}">'.format(
                            scls, sid ) )

                hid = file_parser.storage.byte_storage[key]['field']\
                    .replace( '_', '-' )
                    
                out_file.write(
                    '<div class="spacer"></div>' + \
                    '<span class="hex-field hex-field-' + \
                    hid + '">'
                    '<span class="hex-label">' + \
                    file_parser.storage.byte_storage[key]['field'] + \
                    '</span><span class="hex-contents">' + \
                    str( file_parser.storage.byte_storage[key]['value'] ) + \
                    '</span></span>' )

                last_struct = file_parser.storage.byte_storage[key]['struct']
                last_sid = file_parser.storage.byte_storage[key]['sid']

            out_file.write( '<div class="spacer"></div></div></div>' )

            out_file.write( '</body></html>' )

if '__main__' == __name__:
    main()

