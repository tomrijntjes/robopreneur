$(document).ready(function(){
    $('#merchant_product_post_form').submit(function(){

        var form = $(this);
        var action = form.attr('action');
        var inputs = form.find('textarea, input[type=text]');

        inputs.removeClass('error').attr('title', '');
        $('.success_message').hide();

        $.ajax({
            type: 'POST',
            data: form.serialize(),
            url: action,
            success: function(response){
                if(response.success){
                    $('.success_message').show();
                    inputs.val('');
                }else{
                    $.each(response.data, function(key, error){
                        form.find('textarea[name='+key+']').addClass('error').attr('title', error);
                        form.find('input[name='+key+']').addClass('error').attr('title', error);
                    });
                }
            }
        })

        return false;
    });
});

$(window).scroll(function(){
    scrollTop = $(window).scrollTop();
    commentTeaser = $('.comment_teaser');

    if(scrollTop > 150){
        commentTeaser.fadeOut();
    }else{
        commentTeaser.fadeIn();
    }
});