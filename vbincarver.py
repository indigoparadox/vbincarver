#!/usr/bin/env python3

import yaml
import argparse
import logging
import pprint
import re
from collections import OrderedDict

COLUMN_LEN = 20

class FileParserStorage( object ):

    def __init__( self ):
        self.field_storage = {}
        self.byte_storage = OrderedDict()
        self.sz_storage = {}

    def has_struct( self, key : str ):
        return key in self

    def get_field( self, key : tuple ):
        
        logger = logging.getLogger( 'storage.get' )

        logger.debug( 'getting field: %s', key )

        # We don't process the #-replacer here, so ditch it for now.
        key = (key[0], re.sub( '#.*', '', key[1] ))
        
        return self.field_storage[key[0]]['fields'][key[1]]

    def store_field( self, struct_key : str, field_key : str, val : int ):
        logger = logging.getLogger( 'storage.store' )
        logger.debug( 'storing field %s/%s value %s...',
            struct_key, field_key, str( val ) )
        if struct_key in self.field_storage:
            if field_key in self.field_storage[struct_key]['fields']:
                self.field_storage[struct_key]['fields'][field_key].append(
                    val )
            else:
                self.field_storage[struct_key]['fields'][field_key] = [val]
        else:
            self.field_storage[struct_key] = {'fields': {field_key: [val]}}

    def store_offset(
        self, offset : int, sz : int, struct : str, field : str, val : int, 
        sid: int, sum_to_last: bool
    ):
        bs_items = list( self.byte_storage.items() )
        if sum_to_last and \
        0 < len( self.byte_storage ) and \
        bs_items[-1][1]['field'] == field and \
        bs_items[-1][1]['struct'] == struct and \
        bs_items[-1][1]['sid'] == sid:
            self.byte_storage[bs_items[-1][0]]['size'] += sz
            self.byte_storage[bs_items[-1][0]]['value'] = ''
        else:
            self.byte_storage[offset] = {'struct': struct, 'size': sz,
                'sid': sid, 'field': field, 'value': val}

class ChunkFinder( object ):

    ''' Special ring buffer for finding the start of chunks. '''

    def __init__( self, owner ):
        self.owner = owner
        self.magic_buf = ''
        self.start_offset = 0
        self.chunk_sz = 4

    def dump( self ):

        logger = logging.getLogger( 'chunk.dump' )

        logger.debug( 'buffer (len %d) starting at %d is now %s%s%s%s...',
            len( self.magic_buf ),
            self.start_offset,
            hex( ord( self.magic_buf[0] ) ) + ' ' \
                if len( self.magic_buf ) > 0 else '',
            hex( ord( self.magic_buf[1] ) ) + ' ' \
                if len( self.magic_buf ) > 1 else '',
            hex( ord( self.magic_buf[2] ) ) + ' ' \
                if len( self.magic_buf ) > 2 else '',
            hex( ord( self.magic_buf[3] ) ) \
                if len( self.magic_buf ) > 3 else '' )

    def push( self, c : int ) -> int:

        logger = logging.getLogger( 'chunk.push' )

        logger.debug( 'pushing %s on buffer...', hex( c ) )
        
        self.magic_buf = self.magic_buf + chr( c )
        if self.chunk_sz < len( self.magic_buf ):
            # Drop first char and push up the start offset.
            self.start_offset += 1
            return self.pop()

        return -1

    def has_bytes( self ) -> bool:
        return len( self.magic_buf )

    def pop( self ) -> int:
        byte_out = self.magic_buf[0]
        if 0 < len( self.magic_buf ):
            self.magic_buf = self.magic_buf[1:]
        else:
            self.magic_buf = '' # Outta bytes!
        return ord( byte_out )

    def peek( self ) -> int:
        if 0 < len( self.magic_buf ):
            return ord( self.magic_buf[0] )
        else:
            return -1

class FileParser( object ):

    def __init__( self, in_file, format_data : dict ):

        self.bytes_written = 0
        self.last_struct = ''
        self.spans_open = []
        self.in_file = in_file
        self.format_data = format_data
        self.storage = FileParserStorage()
        self.buffer = []
        self.chunk_finder = ChunkFinder( self )

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
        assert( len( self.spans_open ) < 3 )
        return span

    def add_span_struct( self, class_in : str, **kwargs ):
        for span in self.spans_open:
            assert( 'struct' != span['class'] )
        self.last_struct = class_in
        span = self._add_span( 'struct', class_in )
        assert( 'fields' in kwargs )
        span['fields'] = dict( kwargs['fields'] ) # Copy!
        if 'check_size' in kwargs:
            span['check_size'] = kwargs['check_size']

    def add_span_field( self, class_in : str, **kwargs ):
        
        # Grab the parent struct class.
        assert( 'struct' == self.spans_open[-1]['type'] )
        struct_class = self.spans_open[-1]['class']

        span = self._add_span( 'field', class_in )
        # TODO: String spans?
        span['contents'] = 0
        span['parent'] = struct_class
        if 'size' in kwargs:
            span['size'] = kwargs['size']
        span['counts_written'] = 0
        if 'lsbf' in kwargs:
            span['lsbf'] = kwargs['lsbf']
        else:
            span['lsbf'] = False
        if 'count_field' in kwargs:
            span['count_field'] = kwargs['count_field'].split( '/' )
        if 'count_mod' in kwargs:
            span['count_mod'] = kwargs['count_mod']
        else:
            span['count_mod'] = 'count_field' # Pass straight thru eval().
        if 'summarize' in kwargs:
            span['summarize'] = kwargs['summarize']
        else:
            span['summarize'] = 'default'
        if 'hidden' in kwargs:
            span['hidden'] = kwargs['hidden']
        else:
            span['hidden'] = False
        if 'format' in kwargs:
            span['format'] = kwargs['format']
        else:
            span['format'] = 'number'
        if 'null_term' in kwargs:
            span['null_term'] = kwargs['null_term']
        else:
            span['null_term'] = False

        # Initialize contents correctly for format.
        if 'string' == span['format']:
            span['contents'] = ''
        elif 'number' == span['format']:
            span['contents'] = 0
        else:
            # This should never happen.
            1 / 0

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

            if 'check_size' in self.spans_open[-1]:
                if self.spans_open[-1]['bytes_written'] != \
                self.spans_open[-1]['check_size']:
                    logger.warning(
                        'incorrect size for struct %s: %d (should be %d)',
                        self.spans_open[-1]['class'],
                        self.spans_open[-1]['bytes_written'],
                        self.spans_open[-1]['check_size'] )

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
        #self.out_file.write( '</span>' )

        # Structs just get popped.
        if 'field' != span['type']:
            self._pop_span()
            return

        # Store field contents for later if requested.
        self.storage.store_field(
            span['parent'], span['class'], span['contents'] )

        # Debug for the gnarly index below.
        if 'count_field' in span and \
        '#' in span['count_field'][1]:
            try:
                logger.debug( 'gnarly counts written for %s: %d',
                    re.sub( '.*#', '', span['count_field'][1] ),
                    self.format_data['structs'][
                        re.sub( '.*#', '', span['count_field'][1] )
                    ]['counts_written'] - 1 )
                logger.debug( 'gnarly struct count: %d',
                    self.storage.get_field( span['count_field'] )[
                        self.format_data['structs'][
                            re.sub( '.*#', '', span['count_field'][1] )
                        ]['counts_written'] - 1 \
                    ] )
            except IndexError as e:
                logger.exception( e )
                pass

        # This is kinda gnarly, but if there's a #struct_name in
        # the count_field, then we want to subscript the count_field
        # by the number of that #struct_name read so far, and then
        # use the value stored in the copy of the struct *at that
        # subscripted index* to check if we're still repeating.
        if 'count_field' in span and \
        eval( span['count_mod'],
            {},
            {'count_field':
                self.storage.get_field( span['count_field'] )[
                    self.format_data['structs'][
                        re.sub( '.*#', '', span['count_field'][1] )
                    ]['counts_written'] - 1 \
                    if '#' in span['count_field'][1] else -1
                ] \
            } \
        ) > span['counts_written'] + 1:
            # If this is a field, update counts written and restart
            # if the field says we have some left.

            #logger.debug( 'repeating span %s (%d/%d(%d))...',
            #    span['class'],
            #    span['counts_written'],
            #    self.storage.get_field(
            #        span['count_field'] )[-1],
            #    span['count_mod'] )

            # Refurbish the span to be repeated again.
            #self.format_span( span )
            span['contents'] = 0
            span['bytes_written'] = 0
            span['counts_written'] += 1
    
        else:
            self._pop_span()

    def select_span_struct( self ):

        logger = logging.getLogger( 'parser.select_span.struct' )

        assert( 0 == len( self.spans_open ) )

        self.chunk_finder.dump()

        # We're not inside a struct... So find one!
        for key in self.format_data['structs']:
            struct = self.format_data['structs'][key]

            # Figure out if a new struct is starting.

            # Struct that starts at a static field.
            if 'static' == struct['offset_type'] and \
            self.bytes_written == struct['offset']:
                logger.debug( 'found static struct %s at offset: %d',
                    key, self.bytes_written )
                self.add_span_struct( key, **struct )
                break

            elif 'chunk' == struct['offset_type'] and \
            self.chunk_finder.magic_buf == struct['offset_magic']:
                
                logger.debug( 'found chunk %s starting at offset: %d',
                    self.chunk_finder.magic_buf,
                    self.chunk_finder.start_offset )
                self.add_span_struct( key, **struct )
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
                self.add_span_struct( key, **struct )
                break

            # Struct that starts after a certain other ends.
            elif 'follow' == struct['offset_type'] and \
            (self.chunk_finder.peek() not in struct['first_byte_not'] or \
            self.chunk_finder.peek() in struct['first_byte_is']) and \
            self.last_struct in struct['follows']:
                print( 'fb: {}'.format( hex( self.chunk_finder.peek() ) ) )
                print( 'fbn: {}'.format( struct['first_byte_not'] ) )
                logger.debug( 'struct %s follows struct %s',
                    key, self.last_struct )
                self.add_span_struct( key, **struct )
                break

            # Struct that starts at a field mentioned elsewhere in the
            # file.
            elif 'offset_field' in struct and \
            [x for x in self.storage.get_field(
            struct['offset_field'] ) if x == self.bytes_written]:
                logger.debug( 'struct %s starts at stored field: %d',
                    key, self.storage.get_field(
                    struct['offset_field'] )[0] )
                self.add_span_struct( key, **struct )
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

    def acknowledge_byte( self, byte_in : int ):

        logger = logging.getLogger( 'parser.acknowledge_byte' )

        # Add our byte to the open field contents if there is one.
        if self.spans_open and 'field' == self.spans_open[-1]['type']:
            if 'string' == self.spans_open[-1]['format']:
                self.spans_open[-1]['contents'] += chr( byte_in )
            elif self.spans_open[-1]['lsbf']:
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
        self.buffer.append( (
            byte_in,
            self.spans_open[0]['class'] \
                if 0 < len( self.spans_open ) else None,
            self.format_data\
                ['structs'][self.spans_open[0]['class']]['counts_written'] \
                    if 0 < len( self.spans_open ) else -1,
            self.spans_open[1]['class'] \
                if 1 < len( self.spans_open ) else None,
            self.spans_open[-1]['counts_written'] \
                if 1 < len( self.spans_open ) else None,
            {'hidden': self.spans_open[-1]['hidden']} \
                if 1 < len( self.spans_open ) else {'hidden': False}) )

        # Update accounting.
        self.bytes_written += 1
        for idx in range( len( self.spans_open ) - 1, -1, -1 ):
            self.spans_open[idx]['bytes_written'] += 1

    def _parse_byte( self, file_byte_in : int, find_chunk : bool = True ):

        logger = logging.getLogger( 'parser.parse.byte' )

        if not self.spans_open:
            logger.debug( 'selecting struct...' )
            self.select_span_struct()
        else:
            logger.debug( 'spans open: %s', ','.join( 
                [x['class'] for x in self.spans_open] ) )

        # Don't infinite loop if we're pushing chunk bytes in.
        if find_chunk:
            file_byte = self.chunk_finder.push( file_byte_in )
            logger.debug(
                'swapped %s for %s...',
                hex( file_byte_in ), hex( file_byte ) )
        else:
            file_byte = file_byte_in
            logger.debug( 'skipping chunk finder: %s', hex( file_byte ) )
    
        # Not an elif, as it can run after a new struct is added earlier
        # in this method.
        if self.spans_open and 'struct' == self.spans_open[-1]['type']:
            # We're inside a struct but not a field... so find one!
            logger.debug( 'selecting field...' )
            self.select_span_field( self.spans_open[-1] )
    
        if -1 != file_byte:
            logger.debug( 'acknowledging byte %s...', hex( file_byte ) )
            self.acknowledge_byte( file_byte )
        
        # Start from the end of the open spans so we don't alter
        # the size of the list while working on it.
        for idx in range( len( self.spans_open ) - 1, -1, -1 ):
            span = self.spans_open[idx]

            if 'field' != span['type']:
                logger.debug( 'skipping span %s...', span['class'] )
                continue

            if (span['null_term'] and 0 == file_byte) or \
            (not span['null_term'] and span['bytes_written'] >= span['size']):

                if span['summarize']:
                    # Store info for a summarization stanza.
                    self.storage.store_offset(
                        self.bytes_written - \
                            self.spans_open[idx]['bytes_written'],
                        span['bytes_written'],
                        self.spans_open[-2]['class'] \
                            if len( self.spans_open ) > 1 else None,
                        span['class'],
                        span['contents'],
                        self.format_data\
                            ['structs'][span['parent']]['counts_written'],
                        span['summarize'] == 'sum_repeat' )

                self.close_span( idx )
                if not self.spans_open:
                    # We must've popped the parent struct, too!
                    logger.debug( 'no spans left to process!' )
                    break

    def parse( self ):

        logger = logging.getLogger( 'parser.parse' )

        for file_byte in self.in_file:
            #print( hex( file_byte ) )
            self._parse_byte( file_byte )

        # Empty out the chunk finder!
        while self.chunk_finder.has_bytes():
            logger.debug(
                'shaking out the chunk finder (%d left!)...',
                self.chunk_finder.has_bytes() )
            self._parse_byte( self.chunk_finder.pop(), find_chunk=False )

class HexFormatter( object ):

    def __init__( self, out_file, parser : FileParser ):
    
        self.out_file = out_file
        self.parser = parser
        self.bytes_written = 0
        self.last_struct = None
        self.last_struct_id = None
        self.last_field = None
        self.last_field_id = None

    def break_line( self ):

        if self.last_struct:
            self.close_span()
        if self.last_field:
            self.close_span()

        self.out_file.write( '</div>\n <div class="hex-line">\n' )

        if self.last_struct:
            self.open_span( 'struct', self.last_struct, self.last_struct_id )
        if self.last_field:
            self.open_span( 'field', self.last_field )

    def close_span( self, ind : int = 0 ):
        for i in range( 0, ind ):
            self.out_file.write( ' ' )
        self.out_file.write( '</span>\n' )

    def open_span(
        self, type_in : str, class_in : str, sid_in : int = 0, ind : int = 0
    ):

        sid = ''
        if 'struct' == type_in:
            sid = ' hex-struct-{}-{}'.format(
                class_in.replace( '_', '-' ), str( sid_in ) )

        for i in range( 0, ind ):
            self.out_file.write( ' ' )

        self.out_file.write( '<span class="hex-{} hex-{}-{}{}">\n'.format(
            type_in, type_in, class_in.replace( '_', '-' ), sid ) )

    def write_header( self ):

        self.out_file.write( '<!DOCTYPE html>\n<html>\n<head>\n' )
        self.out_file.write( '<link rel="stylesheet" href="hex.css" />\n' )
        self.out_file.write( '<script src="https://code.jquery.com/jquery-3.7.1.min.js" integrity="sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo=" crossorigin="anonymous"></script>\n' )
        self.out_file.write( '<script src="hex.js"></script>\n' )
        self.out_file.write( '</head>\n<body>\n' )

    def write_footer( self ):
        pass

    def write_layout( self ):

        self.out_file.write( '<div class="hex-layout">\n' )
        self.out_file.write( ' <div class="hex-line">\n' )

        for buf_tup in self.parser.buffer:
            # Break up lines.
            if 0 == self.bytes_written % COLUMN_LEN and \
            0 != self.bytes_written:
                self.break_line()

            # Close last struct if it was open.
            if (self.last_struct != buf_tup[1] or \
            self.last_struct_id != buf_tup[2]) and \
            None != self.last_struct:
                self.close_span( ind=2 )

            # Close last field if it was open.
            if (self.last_field != buf_tup[3] or \
            self.last_field_id != buf_tup[4]) and \
            None != self.last_field:
                self.close_span( ind=3 )

            # Don't write next byte if hidden.
            # TODO: Write the first 3 or so of a repeating pattern? Placehold?
            if buf_tup[5]['hidden']:
                continue

            # See if we can open a new struct.
            if (self.last_struct != buf_tup[1] or \
            self.last_struct_id != buf_tup[2]) and \
            buf_tup[1]:
                self.open_span( 'struct', buf_tup[1], buf_tup[2], ind=2 )

            # See if we can open a new field.
            if (self.last_field != buf_tup[3] or \
            self.last_field_id != buf_tup[4]) and \
            buf_tup[3]:
                self.open_span( 'field', buf_tup[3], ind=3 )

            self.out_file.write(
                '    <span class="{}">{}</span>\n'.format(
                    'byte' if buf_tup[1] else 'byte_free',
                    hex( buf_tup[0] ).lstrip( '0x' ).zfill( 2 ) ) )

            self.bytes_written += 1
            self.last_struct = buf_tup[1]
            self.last_struct_id = buf_tup[2]
            self.last_field = buf_tup[3]
            self.last_field_id = buf_tup[4]

        self.out_file.write( '</div></div>' )

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

    logger.debug( 'starting...' )

    format_data = None
    with open( args.format, 'r' ) as format_file:
        format_data = yaml.load( format_file, Loader=yaml.Loader )
        for key in format_data['structs']:
            struct_def = format_data['structs'][key]
            struct_def['counts_written'] = 0
            if 'offset_field' in struct_def:
                struct_def['offset_field'] = \
                    struct_def['offset_field'].split( '/' )
            if 'count_field' in struct_def:
                struct_def['count_field'] = \
                    struct_def['count_field'].split( '/' )
            if 'first_byte_not' not in struct_def:
                struct_def['first_byte_not'] = []
            if 'first_byte_is' not in struct_def:
                struct_def['first_byte_is'] = []

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

