
import logging
import re
import pprint
from collections import OrderedDict

class FileParserStorage( object ):

    def __init__( self ):
        self.field_storage = {}
        self.byte_storage = OrderedDict()
        self.byte_storage_idx = {}
        self.sz_storage = {}

    def has_struct( self, key : str ):
        return key in self

    def get_field( self, struct_key : str, field_key : str ):
        
        logger = logging.getLogger( 'storage.get' )

        logger.debug( 'getting field: %s/%s', struct_key, field_key )

        # We don't process the #-replacer here, so ditch it for now.
        field_key = re.sub( '#.*', '', field_key )

        try:
            return self.field_storage[struct_key]['fields'][field_key]
        except KeyError as e:
            logger.warn( e )
            return []

    def store_field(
        self, struct_key : str, field_key : str,
        contents : int, mod_contents : str
    ):
        logger = logging.getLogger( 'storage.store' )

        contents = eval( mod_contents,
            {}, {'field_contents': contents } )

        logger.debug( 'storing field %s/%s contents %s...',
            struct_key, field_key, str( contents ) )

        if struct_key in self.field_storage:
            if field_key in self.field_storage[struct_key]['fields']:
                self.field_storage[struct_key]['fields'][field_key].append(
                    contents )
            else:
                self.field_storage[struct_key]['fields'][field_key] = \
                    [contents]
        else:
            self.field_storage[struct_key] = \
                {'fields': {field_key: [contents]}}

    def store_offset(
        self, offset : int, sz : int, struct : str, field : str, fid : int,
        contents : int, mod_contents : str, sid : int, summarize : str,
        format_in : str, lsbf_in : bool
    ):
        prev_offset = list( self.byte_storage.items() )

        contents = eval( mod_contents,
            {}, {'field_contents': contents } )

        if 'sum_repeat' == summarize and \
        0 < len( self.byte_storage ) and \
        prev_offset[-1][1]['field'] == field and \
        prev_offset[-1][1]['struct'] == struct and \
        prev_offset[-1][1]['sid'] == sid:
            self.byte_storage[prev_offset[-1][0]]['size'] += sz
            self.byte_storage[prev_offset[-1][0]]['contents'] = None

        elif 'first_only' == summarize and \
        struct in self.byte_storage_idx and \
        not sid in self.byte_storage_idx[struct]:
            return

        else:
            if struct in self.byte_storage_idx and \
            not sid in self.byte_storage_idx[struct]:
                self.byte_storage_idx[struct][sid] = offset
            elif not struct in self.byte_storage_idx:
                self.byte_storage_idx[struct] = {sid: offset}

            self.byte_storage[offset] = {'struct': struct, 'size': sz,
                'sid': sid, 'field': field, 'fid': fid,
                'contents': contents, 'summarize': summarize, 
                'format': format_in, 'lsbf': lsbf_in}

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
        
        # Only push positive bytes.
        if 0 <= c:
            self.magic_buf = self.magic_buf + chr( c )

        if self.chunk_sz < len( self.magic_buf ) or 0 > c:
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
        self.last_struct_match_miss = []
        self.last_field = None
        self.spans_open = []
        self.in_file = in_file
        self.format_data = format_data
        self.storage = FileParserStorage()
        self.buffer = []
        self.chunk_finder = ChunkFinder( self )

    def _add_span( self, type_in : str, class_in : str ):
        logger = logging.getLogger( 'parser.add.span' )
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

    def _set_last_field( self, field_tuple : tuple ):
        logger = logging.getLogger( 'parser.set.last_field' )
        logger.debug( 'resetting last field to %s (was %s)...',
            field_tuple[0] if field_tuple else None,
            self.last_field[0] if self.last_field else None )
        self.last_field = field_tuple

    def add_span_struct( self, class_in : str, **kwargs ):
        
        logger = logging.getLogger( 'parser.add.struct' )

        for span in self.spans_open:
            assert( 'struct' != span['class'] )

        self.last_struct = class_in
        self.last_struct_match_miss = []

        self._set_last_field( None )

        span = self._add_span( 'struct', class_in )
        assert( 'fields' in kwargs )
        span['fields'] = dict( kwargs['fields'] ) # Copy!
        span['summarize'] = kwargs['summarize']
        for field in span['fields']:
            span['fields'][field]['counts_written'] = 0
        if 'check_size' in kwargs:
            span['check_size'] = kwargs['check_size']

    def add_span_field( self, class_in : str, **kwargs ):

        logger = logging.getLogger( 'parser.add.field' )
        
        # Grab the parent struct class.
        assert( 'struct' == self.spans_open[-1]['type'] )

        span = self._add_span( 'field', class_in )
        span['lsbf'] = kwargs['lsbf']
        span['count_mod'] = kwargs['count_mod']
        span['hidden'] = kwargs['hidden']
        span['format'] = kwargs['format']
        span['term_style'] = kwargs['term_style']
        span['counts_written'] = kwargs['counts_written']
        span['parent'] = kwargs['parent']
        span['mod_contents'] = kwargs['mod_contents']
        span['summarize'] = kwargs['summarize']
        if 'size' in kwargs:
            span['size'] = kwargs['size']
        if 'count_field' in kwargs:
            span['count_field'] = kwargs['count_field']

        # Initialize contents correctly for format.
        if 'string' == span['format']:
            span['contents'] = ''
        elif 'number' == span['format']:
            span['contents'] = 0
        elif 'color' == span['format']:
            span['contents'] = 0
        else:
            logger.error( 'invalid format specified!' )

    def span_key( self, span : dict ):

        ''' Return the full heirarchal path to the given span. '''

        return '{}/{}'.format( span['parent'], span['class'] ) \
            if 'field' == span['type'] else span['class']

    def close_span( self, idx: int ):
    
        ''' Close or repeat a span as the rules dictate. '''

        logger = logging.getLogger( 'parser.close_span' )

        # Some convenience handlers.
        span = self.spans_open[idx]
        span_key = self.span_key( span )

        logger.debug( 'closing span: %s after %d bytes',
            span_key, self.spans_open[idx]['bytes_written'] )

        if 'struct' == span['type']:
            self.format_data['structs'][span['class']]['counts_written'] += 1

        # Structs just get popped.
        if 'field' == span['type']:
            # Store field contents for later if requested.
            self.storage.store_field(
                span['parent'], span['class'], span['contents'],
                span['mod_contents'] )

            # Stow last contents in field def.
            self.spans_open[-2]['fields_written'] \
                [span['class']]['last_contents'] = span['contents']

        # Actually remove the span.
        self.spans_open.pop( idx )

        if self.spans_open and \
        'fields' in self.spans_open[-1]:

            # See if the final field is zero-length.
            if 1 == len( self.spans_open[-1]['fields'] ):
                key = list( self.spans_open[-1]['fields'].keys() )[-1]
                field = self.spans_open[-1]['fields'][key]

                # Also check conditions from select_span_field() to see
                # if last field won't appear.

                if 'count_field' in field and \
                0 == self.lookup_count_field( key, field ):
                    # This field should never appear!
                    del self.spans_open[-1]['fields'][key]

                if 'match_field' in field and \
                not self.match_byte(
                self.storage.get_field(
                    field['match_field'][0],
                    field['match_field'][1] ),
                field['match_field'][1], field, 'match_field' ):
                    # This field should never appear!
                    del self.spans_open[-1]['fields'][key]

            # Finally, see if we're out of fields and close struct if so.
            if not self.spans_open[-1]['fields']:

                #if 'check_size' in self.spans_open[-1]:
                #    if self.spans_open[-1]['bytes_written'] != \
                #    self.spans_open[-1]['check_size']:
                #        logger.warning(
                #            'incorrect size for struct %s: %d (should be %d)',
                #            self.spans_open[-1]['class'],
                #            self.spans_open[-1]['bytes_written'],
                #            self.spans_open[-1]['check_size'] )

                # Parent struct has no more fields. Close the parent
                # struct.
                if not self._last_field_repeats():
                    self.close_span( -1 )

    def match_byte(
        self, c : int, key : str, span : dict, field_match : str = 'first'
    ):

        logger = logging.getLogger( 'parser.match.byte' )

        if type( c ) == list:
            c = c[-1]
            logger.debug( 'interpreting list as: %s', hex( c ) )

        logger.debug( 'comparing byte: %s', hex( c ) )

        if field_match + '_byte_is' in span and \
        c not in span[field_match + '_byte_is']:
            logger.debug( '%s %s byte is %s: negative match (%s)!',
                key, field_match, hex( c ), ','.join(
                    [hex( x ) for x in span[field_match + '_byte_is']] ) )
            return False

        if field_match + '_byte_is_and' in span and \
        not [x for x in span[field_match + '_byte_is_and'] if x == c & x]:
            logger.debug(
                '%s %s byte is %s (AND): negative match (%s)!',
                key, field_match, hex( c ), ','.join(
                    [hex( x ) for x in span[field_match + '_byte_is_and']] ) )
            return False

        if field_match + '_byte_not' in span and \
        c in span[field_match + '_byte_not']:
            logger.debug(
                '%s %s byte is %s: negative match (not %s)!',
                key, field_match, hex( c ), ','.join( 
                    [hex( x ) for x in span[field_match + '_byte_not']] ) )
            return False

        if field_match + '_byte_not_and' in span and \
        [x for x in span[field_match + '_byte_not_and'] if x == c & x]:
            logger.debug(
                '%s %s byte is %s: negative match (not %s)!',
                key, field_match, hex( c ), ','.join( 
                    [hex( x ) for x in \
                        span[field_match + '_byte_not_and']] ) )
            return False

        if field_match + '_byte_gt' in span and \
        c <= span[field_match + '_byte_gt']:
            logger.debug( '%s %s byte is %s: negative match (gt %s)!',
                key, field_match, hex( c ),
                hex( span[field_match + '_byte_gt'] ) )
            return False

        if field_match + '_byte_lt' in span and \
        c >= span[field_match + '_byte_lt']:
            logger.debug( '%s %s byte is %s: negative match (lt %s)!',
                key, field_match, hex( c ),
                hex( span[field_match + '_byte_lt'] ) )
            return False

        return True

    def select_span_struct( self ):

        logger = logging.getLogger( 'parser.select.span.struct' )

        assert( 0 == len( self.spans_open ) )

        self.chunk_finder.dump()

        logger.debug( 'next byte is: %s', hex( self.chunk_finder.peek() ) )

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
            self.match_byte(
                self.chunk_finder.peek(), key, struct ) and \
            self.storage.get_field(
                struct['count_field'][0], struct['count_field'][1] )[-1] > \
            struct['counts_written']:
                logger.debug( 'struct %s repeats %d more times',
                    key,
                    self.storage.get_field(
                    struct['count_field'][0], struct['count_field'][1] )[-1] \
                    - struct['counts_written'] )
                self.add_span_struct( key, **struct )
                break

            # Struct that starts at a field mentioned elsewhere in the
            # file.
            elif 'stored' == struct['offset_type'] and \
            'offset_field' in struct and \
            [x for x in self.storage.get_field(
                struct['offset_field'][0], struct['offset_field'][1] ) \
            if x == self.bytes_written]:
                logger.debug( 'struct %s starts at stored field: %d',
                    key, self.storage.get_field(
                        struct['offset_field'][0], struct['offset_field'][1]
                    )[0] )
                self.add_span_struct( key, **struct )
                break

            # Struct that starts after a certain other ends.
            elif 'follow' == struct['offset_type'] and \
            key not in self.last_struct_match_miss and \
            self.match_byte(
                self.chunk_finder.peek(), key, struct ) and \
            self.last_struct in struct['follows']:
                logger.debug( 'struct %s follows struct %s',
                    key, self.last_struct )
                self.add_span_struct( key, **struct )
                break

            logger.debug( 'adding %s to last struct match miss...', key )
            self.last_struct_match_miss.append( key )

    def lookup_count_field( self, key : str, field : dict ):

        logger = logging.getLogger( 'parser.repeats.field' )

        if 'count_field' not in field:
            logger.debug( 'field %s has no count field.', key )
            return -1

        count_field_storage = self.storage.get_field(
            field['count_field'][0], field['count_field'][1] )

        # Tie count field to specific *instance* of a struct if that
        # was specified...
        count_idx = -1
        if '#' in field['count_field'][1]:
            count_struct_key = re.sub( '.*#', '', field['count_field'][1] )
            count_struct = self.format_data['structs'][count_struct_key]
            count_idx = count_struct['counts_written'] - 1
            logger.debug( 'parsed count index %d from structs[%s]...',
                count_idx, count_struct_key )

        return eval( field['count_mod'],
            {}, {
                'count_field': count_field_storage[count_idx],
                'struct': self.spans_open[-1]
            } )

    def _last_field_repeats( self ):

        logger = logging.getLogger( 'parser.repeats.field' )

        key = self.last_field[0]
        field = self.last_field[1]

        logger.debug( 'checking if %s repeats...', key )

        repeat_count = self.lookup_count_field( key, field )
        if 0 > repeat_count:
            return False

        if repeat_count <= self.last_field[1]['counts_written']:
            logger.debug( 'repeat count %d satisfied by written count %d.',
                repeat_count, self.last_field[1]['counts_written'] )
            return False

        logger.debug( 'repeat count %d higher than written count %d...',
            repeat_count, self.last_field[1]['counts_written'] )
        return True

    def _stow_field_def( self, open_struct : dict, key : str ):
        if not 'fields_written' in open_struct:
            open_struct['fields_written'] = {}
        open_struct['fields_written'][key] = open_struct['fields'][key]
        del open_struct['fields'][key]

    def select_span_field( self, open_struct : dict ):
        
        logger = logging.getLogger( 'parser.select.span.field' )

        assert( 'struct' == open_struct['type'] )

        logger.debug( 'selecting field...' )

        if self.last_field and self._last_field_repeats():
            # If this is a field, update counts written and restart
            # if the field says we have some left.

            logger.debug( 'repeating span %s (%d/%d(%s))...',
                self.last_field[0],
                self.last_field[1]['counts_written'],
                self.storage.get_field(
                    self.last_field[1]['count_field'][0],
                    self.last_field[1]['count_field'][1]
                )[-1],
                self.last_field[1]['count_mod'] )

            # Refurbish the span to be repeated again.
            self.last_field[1]['counts_written'] += 1
            logger.debug(
                'incrementing written count on field %s to %d...',
                self.last_field[0], self.last_field[1]['counts_written'] )
            self.add_span_field(
                self.last_field[0], **(self.last_field[1]) )

            return

        # If there's nothing to repeat, then check the open struct for
        # new fields.
        for key in open_struct['fields']:
            field = open_struct['fields'][key]

            # Adding a new condition here should also be reflected in
            # close_span() so we know if a field won't appear and the struct
            # has ended!

            if 'offset' in field and \
            ('match_field' not in field or \
            self.match_byte(
                self.storage.get_field(
                    field['match_field'][0], field['match_field'][1] ),
                field['match_field'][1], field, 'match_field' )) and \
            open_struct['bytes_written'] == field['offset']:
                self.add_span_field( key, **field )
                logger.debug( 'removing used field: %s', key )

                # Remove field now that we've written it.
                open_struct['fields'][key]['counts_written'] += 1
                self._set_last_field( (key, open_struct['fields'][key]) )
                self._stow_field_def( open_struct, key )
                break

            elif 'follows' in field and \
            ('match_field' not in field or \
            self.match_byte(
                self.storage.get_field(
                    field['match_field'][0], field['match_field'][1] ),
                field['match_field'][1], field, 'match_field' )) and \
            self.last_field[0] == field['follows']:

                self.add_span_field( key, **field )
                logger.debug( 'removing used field: %s', key )

                # Remove field now that we've written it.
                open_struct['fields'][key]['counts_written'] += 1
                self._set_last_field( (key, open_struct['fields'][key]) )
                self._stow_field_def( open_struct, key )
                break

        logger.debug( 'selecting field complete.' )

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

    def _parse_byte( self, file_byte_in : int ):

        logger = logging.getLogger( 'parser.parse.byte' )

        if not self.spans_open:
            logger.debug( 'selecting struct...' )
            self.select_span_struct()
        else:
            logger.debug( 'spans open: %s', ','.join( 
                [x['class'] for x in self.spans_open] ) )

        # Not an elif, as it can run after a new struct is added earlier
        # in this method.
        if self.spans_open and 'struct' == self.spans_open[-1]['type']:
            # We're inside a struct but not a field... so find one!
            logger.debug( 'selecting field...' )
            self.select_span_field( self.spans_open[-1] )
        else:
            logger.debug( 'not selecting field!' )

        # Don't infinite loop if we're pushing chunk bytes in.
        file_byte = self.chunk_finder.push( file_byte_in )
        logger.debug(
            'swapped %s for %s...',
            hex( file_byte_in ), hex( file_byte ) )
    
        # TODO ('var' == span['term_style'] and 0x80 != (0x80 & file_byte)):
        # OR away continue byte?
    
        if -1 != file_byte:
            logger.debug( 'acknowledging byte %s...', hex( file_byte ) )
            self.acknowledge_byte( file_byte )
        
        # Start from the end of the open spans so we don't alter
        # the size of the list while working on it.
        for idx in range( len( self.spans_open ) - 1, -1, -1 ):
            span = self.spans_open[idx]

            if 'struct' == span['type']:
                logger.debug( 'skipping closing span %s...', span['class'] )
                continue

            if ('on_null' == span['term_style'] and 0 == file_byte) or \
            ('static' == span['term_style'] and \
            span['bytes_written'] >= span['size']) or \
            ('var' == span['term_style'] and 0x80 != (0x80 & file_byte)):
                parent = self.spans_open[0]
                parent_def = self.format_data['structs'][span['parent']]

                if 'none' != parent_def['summarize']:
                    # Store info for a summarization stanza.
                    self.storage.store_offset(
                        self.bytes_written - \
                            self.spans_open[idx]['bytes_written'],
                        span['bytes_written'],
                        span['parent'],
                        span['class'],
                        span['counts_written'],
                        span['contents'],
                        span['mod_contents'],
                        parent_def['counts_written'],
                        parent_def['summarize'] \
                            if 'default' == span['summarize'] else \
                            span['summarize'],
                        span['format'],
                        span['lsbf'] )

                self.close_span( idx )
                if not self.spans_open:
                    # We must've popped the parent struct, too!
                    logger.debug( 'no spans left to process!' )
                    break

        logger.debug( 'processing byte complete!' )

    def parse( self ):

        logger = logging.getLogger( 'parser.parse' )

        last_byte = None
        for file_byte in self.in_file:
            self._parse_byte( file_byte )
            last_byte = file_byte

        logger.debug( 'last byte was: %s, chunk_finder next byte is: %s',
            last_byte, self.chunk_finder.peek() )

        # Empty out the chunk finder!
        while self.chunk_finder.has_bytes():
            logger.debug(
                'shaking out the chunk finder (%d left!)...',
                self.chunk_finder.has_bytes() )
            self._parse_byte( -1 )

