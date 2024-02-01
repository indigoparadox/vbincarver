
import os
import yaml
import logging
import pprint
import importlib.resources

class FormatConfig( object ):

    def open_format( self, path ):
        try:
            # TODO: This is untested since we're on Python 3.8.
            return importlib.resources.files( __package__ + '.formats' )\
                .joinpath( path ).open( 'r', encoding=encoding )
        except AttributeError:
            return importlib.resources.read_text(
                __package__ + '.formats', path )

    def __init__( self, parse_path : str, format_name : str = None ):

        logger = logging.getLogger( 'config.format' )

        format_file = None
        if format_name:
            format_file = self.open_format( format_name + '.yaml' )
        else:
            file_ext = os.path.splitext( parse_path )[1]
            format_file = self.open_format( file_ext[1:].lower() + '.yaml' )
        assert( None != format_file )

        self.format_data = yaml.load( format_file, Loader=yaml.Loader )

        # Merge included files.
        if 'include' in self.format_data:
            for src in self.format_data['include']:
                import_file = self.open_format( src )
                logger.debug( 'importing %s...', src )
                import_data = yaml.load( import_file, Loader=yaml.Loader )
                self.merge_subtree( import_data )

        # Shore up data.
        self.fix_missing_fields( self.format_data )

    def fix_missing_fields( self, format_data : dict ):

        ''' Fill in fields not required in definition file. '''

        for struct_key in format_data['structs']:
            struct_def = format_data['structs'][struct_key]
            struct_def['counts_written'] = 0
            if 'offset_field' in struct_def:
                struct_def['offset_field'] = \
                    struct_def['offset_field'].split( '/' )
            if 'count_field' in struct_def:
                struct_def['count_field'] = \
                    struct_def['count_field'].split( '/' )
            if 'summarize' not in struct_def:
                struct_def['summarize'] = 'default'
            assert( struct_def['summarize'] in \
                ['sum_repeat', 'first_only', 'none', 'no_fields', 'default'] )

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
                if 'mod_contents' not in field_def:
                    field_def['mod_contents'] = 'field_contents'
                if 'summarize' not in field_def:
                    field_def['summarize'] = 'default'
                assert( field_def['summarize'] in \
                    ['sum_repeat', 'first_only', 'none', 'default'] )

    def merge_subtree(
        self, import_data : dict, format_key : str = 'root',
        format_data : dict = None
    ):

        ''' Merge import data into existing format data, but existing data
        takes precedence. '''

        logger = logging.getLogger( 'config.format.merge' )

        if not format_data:
            logger.debug( 'using root format data...' )
            format_data = self.format_data

        for key in import_data:
            if dict == type( import_data[key] ) and key in format_data:
                logger.debug(
                    'merging key %s from import into format data %s...',
                    key, format_key )
                self.merge_subtree( import_data[key], key, format_data[key] )
            elif not key in format_data:
                logger.debug( 'using key %s from import data %s...',
                    key,format_key )
                format_data[key] = import_data[key]

    def __getitem__( self, index ):
        return self.format_data[index]

