# -*- coding: utf-8 -*-
import os, logging
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
            InlineQueryResultCachedPhoto, InlineQueryResultArticle, InputTextMessageContent)
from telegram.ext import Updater, CommandHandler, ChosenInlineResultHandler, InlineQueryHandler, MessageHandler, Filters
import re

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

token = os.environ['TELEGRAM_TOKEN']


#----------- SETUP POSTGRESQL CONNECTION
from urllib import parse
import psycopg2

parse.uses_netloc.append("postgres")
url = parse.urlparse(os.environ["DATABASE_URL"])

conn = psycopg2.connect(
    database=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port
)
c = conn.cursor()
#-------------------



temp = {}
to_be_whispers = {}
whispers = []

def get_whisper(m_id, c_id):
    c.execute('select * from whispers where message_id = %s and chat_id = %s;',
                (m_id, c_id))
    return c.fetchone()

def inline_query(bot, update):
    query = update.inline_query.query
    if re.match(r'^show \d+ \d+$', query):
        if not get_whisper(query.split()[1], query.split()[2]):
            bot.answerInlineQuery(
                update.inline_query.id,
                results=[InlineQueryResultArticle(
                            id=update.inline_query.id + 'notf',
                            title='Photo not found',
                            input_message_content=InputTextMessageContent('ماكو هيج صورة')
                        )]
            )
            return
            
        sender_id, receiver, message_id, chat_id = get_whisper(query.split()[1], query.split()[2])
        if str(update.inline_query.from_user.id) == str(sender_id) or str(update.inline_query.from_user.username) == str(receiver):
            bot.answerInlineQuery(
                update.inline_query.id,
                results=[],
                switch_pm_text='Show Photo',
                switch_pm_parameter='{0[1]}_{0[2]}show'.format(query.split())
            )
            return
        else:
            bot.answerInlineQuery(
                update.inline_query.id,
                results=[InlineQueryResultArticle(
                    id=update.inline_query.id + 'wuser',
                    title='This whisper wasn\'t meant for you',
                    input_message_content=InputTextMessageContent('لتدود')
                )]
            )
            return
    
    if not re.match('^@[0-9a-zA-Z_]+( _)?$', query):
        bot.answerInlineQuery(
                update.inline_query.id,
                results=[InlineQueryResultArticle(
                    id=update.inline_query.id + 'wformat',
                    title='Write the username',
                    input_message_content=InputTextMessageContent('اكتب عدل')
                )]
        )
        return
    results_ = []
    
    if query.endswith(' _'):
        if (update.inline_query.from_user.id) in to_be_whispers:
            sender_id = update.inline_query.from_user.id
            receiver, message_id, chat_id, file_id = to_be_whispers[sender_id]
            results_.append(
                InlineQueryResultCachedPhoto(
                    id=update.inline_query.id + 'photo',
                    photo_file_id=file_id,
                    title='Whisper photo to {}'.format(query[:-2]),
                    input_message_content=InputTextMessageContent('Photo whisper to '+query[:-2]),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton('Show Photo',
                        switch_inline_query_current_chat='show {} {}'.format(message_id, chat_id))
                    ]])
                )
            )
        bot.answerInlineQuery(
            update.inline_query.id,
            results=results_,
            switch_pm_text='Whisper a new photo to {} ..'.format(query[:-2]),
            switch_pm_parameter=query[1:-2]
        )
        return
    else:
       bot.answerInlineQuery(
            update.inline_query.id,
            results=[],
            switch_pm_text='Whisper a new photo to {} ..'.format(query),
            switch_pm_parameter=query[1:]
       )

def start(bot, update, args):
    if args == []:
        bot.sendMessage(chat_id=update.message.chat_id, text='To use the bot, go to a chat and type the username of the bot followed by a space.')
        return
    if re.match(r'^\d+_\d+show$', args[0]):
        m_id, c_id = args[0].split('_')[0], args[0].split('_')[1][:-4]
        bot.forwardMessage(
            chat_id=update.message.chat_id,
            from_chat_id=c_id,
            message_id=m_id
        )
        return
    temp[update.message.from_user.id] = args[0]
    bot.sendMessage(chat_id=update.message.chat_id, text='Send the photo that you want to whisper to @{} or press /cancel to cancel:'.format(args[0]))

def cancel(bot, update):
    if update.message.from_user.id in temp:
        del temp[update.message.from_user.id]
    bot.sendMessage(
        chat_id=update.message.chat_id,
        text='Press the button to go back',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(text='Go back to chat', switch_inline_query='')
        ]])
    )

def insert_whisper_temp(sender_id, receiver, message_id, chat_id, file_id):
    to_be_whispers[sender_id] = (receiver, message_id, chat_id, file_id)

def insert_whisper(sender_id, receiver, message_id, chat_id):
    c.execute('insert into whispers values(%s, %s, %s, %s);', (sender_id, receiver, message_id, chat_id))
    conn.commit()
    
def photo(bot, update):
    if update.message.from_user.id not in temp:
        start(bot, update, [])
        return
    
    #### insert into temp database
    receiver = temp[update.message.from_user.id]
    insert_whisper_temp(
        update.message.from_user.id, 
        receiver, 
        update.message.message_id, 
        update.message.chat_id, 
        update.message.photo[-1].file_id
    )
    bot.sendMessage(
            chat_id=update.message.chat_id,
            text='Done!',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text='Send Whisper ..', switch_inline_query='@' + receiver + ' _')
            ]])
    )
    
def chosen(bot, update):
    if not update.chosen_inline_result.result_id.endswith('photo'):
        return
    sender_id = update.chosen_inline_result.from_user.id
    receiver, message_id, chat_id, file_id = to_be_whispers[sender_id]
    insert_whisper(sender_id, receiver, message_id, chat_id)
    del to_be_whispers[sender_id]
    
def error(bot, update, error):
    logging.warning('Update "%s" caused error "%s"' % (update, error))



updater = Updater(token)

dp = updater.dispatcher
dp.add_handler(InlineQueryHandler(inline_query))
dp.add_handler(CommandHandler('start', start, pass_args=True))
dp.add_handler(CommandHandler('cancel', cancel))
dp.add_handler(ChosenInlineResultHandler(chosen))
dp.add_handler(MessageHandler(Filters.photo, photo))
dp.add_error_handler(error)

# Start the Bot
updater.start_polling()

# Run the bot until the user presses Ctrl-C or the process receives SIGINT,
# SIGTERM or SIGABRT
updater.idle()
