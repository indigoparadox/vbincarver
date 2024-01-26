
import yaml
import logging
import pprint

class FormatConfig( object ):

    def __init__( self, format_path ):

        logger = logging.getLogger( 'config.format' )

        with open( format_path, 'r' ) as format_file:
            format_data = yaml.load( format_file, Loader=yaml.Loader )

            self.format_data = format_data

            # Merge included files.
            if 'include' in format_data:
                for src in format_data['include']:
                    with open( src, 'r' ) as import_file:
                        logger.debug( 'importing %s...', src )
                        import_data = yaml.load(
                            import_file, Loader=yaml.Loader )
                        self.merge_subtree( import_data )

            # Shore up data.
            self.fix_missing_fields( self.format_data )
    
            printer = pprint.PrettyPrinter()
            printer.pprint( format_data )

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

