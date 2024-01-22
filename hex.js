
$(document).ready( function() {
   $('.hex-field').click( function() {

      var parent_class =
         $(this).parent( '.hex-struct' ).attr( 'class' ).split( /\s+/ );
      var sel_class = $(this).attr( 'class' ).split(/\s+/);
      var sel_sel = '.' + parent_class[2] + ' .' + sel_class[1];
      console.log( sel_sel );
      $('.hex-field').removeClass( 'hex-selected' );
      $(sel_sel).addClass( 'hex-selected' );
   } );
} );

