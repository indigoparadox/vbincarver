
from .parser import FileParser

class BytesFormatter( object ):

    def __init__( self, out_file, parser : FileParser ):

        self.out_file = out_file
        self.parser = parser

    def close_tag( self, tag : str, indent : int = 0 ):
        for i in range( 0, indent ):
            self.out_file.write( ' ' )
        self.out_file.write( '</{}>\n'.format( tag ) )

    def close_div( self, indent : int = 0 ):
        self.close_tag( 'div', indent )

    def close_span( self, indent : int = 0 ):
        self.close_tag( 'span', indent )

    def open_tag(
        self, tag : str, class_in : str = None, indent : int = 0,
        data_key : str = None, data : str = None, contents : str = None,
        close : bool = False
    ):

        if contents is None:
            # Don't print "None" literally.
            contents = ''

        for i in range( 0, indent ):
            self.out_file.write( ' ' )
        self.out_file.write(
            '<{}{}{}>{}'.format(
                tag,
                ' data-' + data_key + '="' + data +'"' if data_key else '',
                ' class="' + class_in + '"' if class_in else '',
                contents if contents or close else '\n' ) )
        if close:
            self.out_file.write( '</{}>\n'.format( tag ) )

    def open_div(
        self, class_in : str = None, indent : int = 0,
        data_key : str = None, data : str = None, contents : str = None,
        close : bool = False
    ):
        self.open_tag(
            'div', class_in, indent, data_key, data, contents, close )

    def open_span(
        self, class_in : str = None, indent : int = 0,
        data_key : str = None, data : str = None, contents : str = None,
        close : bool = False
    ):
        self.open_tag(
            'span', class_in, indent, data_key, data, contents, close )

    def format_class( self, str_in : str ) -> str:
        return str_in.replace( '_', '-' )

class HexFormatter( BytesFormatter ):

    INDENT_LINE=1
    INDENT_STRUCT=2
    INDENT_FIELD=3
    INDENT_BYTE=4

    def __init__( self, out_file, parser : FileParser, column_len : int=20 ):

        super().__init__( out_file, parser )
    
        self.bytes_written = 0
        self.last_struct = None
        self.last_struct_id = None
        self.last_field = None
        self.last_field_id = None
        self.column_len = column_len

    def break_line( self ):

        if self.last_field:
            self.close_span( indent=HexFormatter.INDENT_FIELD )
        if self.last_struct:
            self.close_span( indent=HexFormatter.INDENT_STRUCT )

        self.close_div( indent=HexFormatter.INDENT_LINE )
        self.open_div( 'hex-line', indent=HexFormatter.INDENT_LINE )

        if self.last_struct:
            self.open_struct_field_span(
                'struct', self.last_struct, self.last_struct_id,
                indent=HexFormatter.INDENT_STRUCT )
        if self.last_field:
            self.open_struct_field_span( 'field', self.last_field,
                self.last_field_id,
                indent=HexFormatter.INDENT_FIELD )

    def open_struct_field_span(
        self, type_in : str, class_in : str, sid_in : int = 0,
        indent : int = 0
    ):

        sid = ''
        if 'struct' == type_in:
            sid = ' hex-struct-{}-{}'.format(
                class_in.replace( '_', '-' ), str( sid_in ) )
        else:
            sid = ' hex-field-{}-{}'.format(
                class_in.replace( '_', '-' ), str( sid_in ) )

        self.open_span( 'hex-{} hex-{}-{}{}'.format(
            type_in, type_in, class_in.replace( '_', '-' ), sid ),
            indent=indent )

    def write_layout( self ):

        self.open_div( 'hex-layout' )
        self.open_div( 'hex-line', indent=HexFormatter.INDENT_LINE )

        for buf_tup in self.parser.buffer:
            # Break up lines.
            if 0 == self.bytes_written % self.column_len and \
            0 != self.bytes_written:
                self.break_line()

            # Close last struct if it was open.
            if (self.last_struct != buf_tup[1] or \
            self.last_struct_id != buf_tup[2]) and \
            None != self.last_struct:
                self.close_span( indent=HexFormatter.INDENT_STRUCT )

            # Close last field if it was open.
            if (self.last_field != buf_tup[3] or \
            self.last_field_id != buf_tup[4]) and \
            None != self.last_field:
                self.close_span( indent=HexFormatter.INDENT_FIELD )

            # Don't write next byte if hidden.
            # TODO: Write the first 3 or so of a repeating pattern? Placehold?
            if buf_tup[5]['hidden']:
                continue

            # See if we can open a new struct.
            if (self.last_struct != buf_tup[1] or \
            self.last_struct_id != buf_tup[2]) and \
            buf_tup[1]:
                self.open_struct_field_span(
                    'struct', buf_tup[1], buf_tup[2],
                    indent=HexFormatter.INDENT_STRUCT )

            # See if we can open a new field.
            if (self.last_field != buf_tup[3] or \
            self.last_field_id != buf_tup[4]) and \
            buf_tup[3]:
                self.open_struct_field_span(
                    'field', buf_tup[3], buf_tup[4],
                    indent=HexFormatter.INDENT_FIELD )

            self.open_span( 
                'byte' if buf_tup[1] else 'byte_free',
                indent=HexFormatter.INDENT_BYTE,
                contents=hex( buf_tup[0] ).lstrip( '0x' ).zfill( 2 ),
                close=True )

            self.bytes_written += 1
            self.last_struct = buf_tup[1]
            self.last_struct_id = buf_tup[2]
            self.last_field = buf_tup[3]
            self.last_field_id = buf_tup[4]

        if self.last_field:
            self.close_span( indent=HexFormatter.INDENT_FIELD )

        if self.last_struct:
            self.close_span( indent=HexFormatter.INDENT_STRUCT )

        self.close_div( indent=HexFormatter.INDENT_LINE )
        self.close_div()

class SummaryFormatter( BytesFormatter ):

    INDENT_STRUCT = 1
    INDENT_FIELD = 2
    INDENT_FIELD_CONTENTS = 3

    def format_field( self, contents, format_in : str ):
        if 'color' == format_in:
            style = 'background: #{}; width: 10px; height: 10px;'.format(
                hex( contents ).lstrip( '0x' ).zfill( 6 ) )
            contents = '<div style="{}"></div>'.format( style )
        return contents

    def write_struct_head( self, offset : str, hex_byte : dict ):

        storage = self.parser.storage

        struct_class = 'hex-struct-{}'.format(
            self.format_class( hex_byte['struct'] ) )
        sid = '{}-{}'.format( struct_class, hex_byte['sid'] )

        # Start a new struct.
        self.write_spacer( SummaryFormatter.INDENT_STRUCT )
        self.open_div(
            'hex-struct {} {}'.format( struct_class, sid ),
            indent=SummaryFormatter.INDENT_STRUCT )
        self.open_tag(
            'h3', 'hex-struct-title', contents=hex_byte['struct'],
            indent=SummaryFormatter.INDENT_FIELD,
            close=True )
        self.open_div( 'hex-struct-offset',
            contents='@{} ({})'.format( offset, hex( offset ) ),
            indent=SummaryFormatter.INDENT_FIELD,
            close=True )
        self.open_div( 'hex-struct-sz',
            contents='({} bytes)'.format(

                # Sum sizes of all fields in the struct.
                sum( [storage.byte_storage[x]['size'] \
                    for x in storage.byte_storage \
                        if storage.byte_storage[x]['struct'] == \
                            storage.byte_storage[offset]['struct'] and \
                        storage.byte_storage[x]['sid'] == \
                            storage.byte_storage[offset]['sid']] )

                        ), indent=SummaryFormatter.INDENT_FIELD, close=True )

        self.write_spacer( indent=SummaryFormatter.INDENT_FIELD )

    def write_spacer( self, indent : int ):
        self.open_div( 'spacer', contents=' ', indent=indent, close=True )

    def write_layout( self ):

        storage = self.parser.storage

        self.out_file.write( '<div class="hex-fields"><div>' )
        #self.open_div( 'hex-fields'
        last_struct = ''
        for key in storage.byte_storage:

            hex_byte = storage.byte_storage[key]
                
            if storage.byte_storage[key]['struct'] != \
            last_struct or \
            storage.byte_storage[key]['sid'] != \
            last_sid:
                self.close_div( indent=SummaryFormatter.INDENT_STRUCT )
                self.write_struct_head( key, hex_byte )

            if 'no_fields' != hex_byte['summarize']:
                # Write the field.

                self.open_span(
                    'hex-field hex-field-{} hex-field-{}-{}{}'.format(
                        self.format_class( hex_byte['field'] ),
                        self.format_class( hex_byte['field'] ),
                        hex_byte['fid'],
                        ' hex-lsbf' if hex_byte['lsbf'] else '' ),
                    indent=SummaryFormatter.INDENT_FIELD )
                self.open_span(
                    'hex-label', contents=hex_byte['field'],
                    indent=SummaryFormatter.INDENT_FIELD_CONTENTS,
                    close=True )
                self.open_span(
                    'hex-sz', contents='({} bytes)'.format(
                        str( hex_byte['size'] ) ),
                    indent=SummaryFormatter.INDENT_FIELD_CONTENTS,
                    close=True )
                self.open_span(
                    'hex-contents',
                    contents=self.format_field(
                        hex_byte['contents'], hex_byte['format'] ),
                    indent=SummaryFormatter.INDENT_FIELD_CONTENTS,
                    close=True )
                self.close_span( indent=SummaryFormatter.INDENT_FIELD )

                self.write_spacer( indent=SummaryFormatter.INDENT_FIELD )

            last_struct = storage.byte_storage[key]['struct']
            last_sid = storage.byte_storage[key]['sid']

        if last_struct:
            self.close_div( indent=SummaryFormatter.INDENT_STRUCT )

        self.close_div() # hex-fields

