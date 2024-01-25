
from .parser import FileParser

class HexFormatter( object ):

    def __init__( self, out_file, parser : FileParser, column_len : int=20 ):
    
        self.out_file = out_file
        self.parser = parser
        self.bytes_written = 0
        self.last_struct = None
        self.last_struct_id = None
        self.last_field = None
        self.last_field_id = None
        self.column_len = column_len

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
            if 0 == self.bytes_written % self.column_len and \
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


