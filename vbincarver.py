#!/usr/bin/env python3

import yaml
import argparse
import logging

COLUMN_LEN = 20

class FileParser( object ):

    def __init__( self, in_file, out_file, format_data : dict ):

        self.bytes_written = 0
        self.last_struct = ''
        self.spans_open = []
        self.out_file = out_file
        self.in_file = in_file
        self.format_data = format_data
        self.stored_offsets = {}

    def write_header( self ):

        self.out_file.write( '<!DOCTYPE html><html><head>' )
        self.out_file.write( '<link rel="stylesheet" href="hex.css" />' )
        self.out_file.write( '</head><body>' )
        self.out_file.write( '<div class="hex-layout">' )

    def _add_span( self, type_in : str, class_in : str, sz : int ):
        logger = logging.getLogger( 'parser.add_span' )
        logger.debug( 'adding span for %s: %s (%d bytes)',
            type_in, class_in, sz )
        span = {
            'class': class_in,
            'type': type_in,
            'size': sz,
            'written': 0
        }
        self.spans_open.append( span )
        self.format_span( span )
        return span

    def add_span_struct( self, class_in : str, sz : int, offsets : dict ):
        for span in self.spans_open:
            assert( 'struct' != span['class'] )
        self.last_struct = class_in
        span = self._add_span( 'struct', class_in, sz )
        span['offsets'] = dict( offsets ) # Copy!

    def add_span_offset( self, class_in : str, **kwargs ):
        
        # Grab the parent struct class.
        assert( 'struct' == self.spans_open[-1]['type'] )
        struct_class = self.spans_open[-1]['class']

        span = self._add_span( 'offset', class_in, kwargs['size'] )
        # TODO: String spans?
        span['contents'] = 0
        span['parent'] = struct_class
        if 'lsbf' in kwargs:
            span['lsbf'] = kwargs['lsbf']
        if 'store' in kwargs:
            span['store'] = kwargs['store']

    def pop_span( self, idx: int ):

        logger = logging.getLogger( 'parser.pop_span' )

        # Some convenience handlers.
        span = self.spans_open[idx]
        span_key = '{}/{}'.format( span['parent'], span['class'] ) \
            if 'offset' == span['type'] else span['class']

        logger.debug( 'closing span: %s after %d bytes',
            span_key, span['written'] )

        if 'struct' == span['type']:
            self.format_data['structs'][span['class']]['counts_written'] += 1

        # Store offset contents for later if requested.
        if 'store' in span.keys() and span['store']:
            logger.debug( 'storing offset %s/%s value %d...',
                span['parent'], span['class'], span['contents'] )
            if span_key in self.stored_offsets:
                self.stored_offsets[span_key].append( span['contents'] )
            else:
                self.stored_offsets[span_key] = [span['contents']]

        # Write the closing span and pop the span off the open list.
        self.out_file.write( '</span>' )
        self.spans_open.pop( idx )

    def format_span( self, span : dict ):
        self.out_file.write(
            '<span class="{} {}-{}">'.format(
                span['type'], span['type'],
                span['class'].replace( '_', '-' ) ) )

    def break_line( self ):

        for span in self.spans_open:
            self.out_file.write( '</span>' )
        self.out_file.write( '</div><div class="hex-line">' )
        for span in self.spans_open:
            self.format_span( span )

    def format_byte( self, byte_in : int ):

        logger = logging.getLogger( 'parser.format_byte' )

        if not self.spans_open:
            # We're not inside a struct... So find one!
            for key in self.format_data['structs']:
                struct = self.format_data['structs'][key]

                # Figure out if a new struct is starting.

                # Struct that starts at a static offset.
                if 'static' == struct['offset_type'] and \
                self.bytes_written == struct['offset']:
                    logger.debug( 'found static struct %s at offset: %d',
                        key, self.bytes_written )
                    self.add_span_struct(
                        key, struct['size'], struct['fields'] )
                    break

                # Struct that repeats based on contents of other offset.
                elif self.last_struct == key and \
                'count_field' in struct and \
                struct['count_field'] in self.stored_offsets and \
                self.stored_offsets[struct['count_field']][0] > \
                struct['counts_written']:
                    logger.debug( 'struct %s repeats %d more times',
                        key,
                        self.stored_offsets[struct['count_field']][0] - \
                        struct['counts_written'] )
                    self.add_span_struct(
                        key, struct['size'], struct['fields'] )

                # Struct that starts after a certain other ends.
                elif 'follow' == struct['offset_type'] and \
                self.last_struct == struct['follows']:
                    logger.debug( 'struct %s follows struct %s',
                        key, self.last_struct )
                    self.add_span_struct(
                        key, struct['size'], struct['fields'] )
                    break

                # Struct that starts at an offset mentioned elsewhere in the
                # file.
                elif 'offset_field' in struct and \
                struct['offset_field'] in self.stored_offsets and \
                [x for x in self.stored_offsets[struct['offset_field']] \
                if x == self.bytes_written]:
                    logger.debug( 'struct %s starts at stored offset: %d',
                        key, self.stored_offsets[struct['offset_field']][0] )
                    self.add_span_struct(
                        key, struct['size'], struct['fields'] )
                    break


        if self.spans_open:
            open_span = self.spans_open[-1]

            # Not an elif, as it can run after a new struct is added earlier
            # in this method.
            if 'struct' == open_span['type']:
                # We're inside a struct but not an offset... so find one!
                if open_span['offsets']:
                    for key in open_span['offsets']:
                        offset = open_span['offsets'][key]
                        if open_span['written'] == offset['offset']:
                            self.add_span_offset( key, **offset )
                            logger.debug( 'removing used offset: %s', key )

                            # Remove offset now that we've written it.
                            del open_span['offsets'][key]
                            break

        # Add our byte to the open offset contents if there is one.
        if self.spans_open and 'offset' == self.spans_open[-1]['type']:
            if 'lsbf' in self.spans_open[-1] and self.spans_open[-1]['lsbf']:
                # Shift byte before adding it.
                self.spans_open[-1]['contents'] |= \
                    (byte_in << self.spans_open[-1]['written'] * 8)
            else:
                self.spans_open[-1]['contents'] <<= 8
                self.spans_open[-1]['contents'] |= byte_in
            #logger.debug( 'current offset %s/%s contents: 0x%08x',
            #    self.spans_open[-1]['parent'], self.spans_open[-1]['class'],
            #    self.spans_open[-1]['contents'] )

        # Write our byte.
        self.out_file.write( hex( byte_in ).lstrip( '0x' ).zfill( 2 ) )

    def parse( self ):

        logger = logging.getLogger( 'parser.parse' )
    
        self.write_header()
        self.out_file.write( '<div class="hex-line">' )
        for file_byte in self.in_file:
            # Break up lines.
            if 0 == self.bytes_written % COLUMN_LEN and \
            0 != self.bytes_written:
                self.break_line()

            self.format_byte( file_byte )
           
            # Update accounting.
            self.bytes_written += 1
                
            # Start from the end of the open spans so we don't alter
            # the size of the list while working on it.
            for idx in range( len( self.spans_open ) - 1, -1, -1 ):
                self.spans_open[idx]['written'] += 1
                if self.spans_open[idx]['written'] >= \
                self.spans_open[idx]['size']:
                    self.pop_span( idx )

        self.out_file.write( '</div></div></body>' )

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument( '-f', '--format', action='store' )

    parser.add_argument( '-o', '--out-file', action='store' )

    parser.add_argument( 'parse_file', action='store' )

    args = parser.parse_args()

    logger = logging.basicConfig( level=logging.DEBUG )

    format_data = None
    with open( args.format, 'r' ) as format_file:
        format_data = yaml.load( format_file, Loader=yaml.Loader )
        for key in format_data['structs']:
            format_data['structs'][key]['counts_written'] = 0

    with open( args.out_file, 'w' ) as out_file:
        with open( args.parse_file, 'rb' ) as parse_file:
            file_parser = FileParser(
                parse_file.read(), out_file, format_data )
            file_parser.parse()

if '__main__' == __name__:
    main()

