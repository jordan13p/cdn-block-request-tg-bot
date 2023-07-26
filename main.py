import os, re
import requests, boto3
import telegram
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler


# get telegram bot token, aws key
TOKEN = os.getenv("TELEGRAM_TOKEN")
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_DEFAULT_REGION = 'us-east-1'
CLOUDFLARE_TOKEN = os.getenv('CLOUDFLARE_TOKEN')
CLOUDFLARE_ZONE_TAG = os.getenv('CLOUDFLARE_ZONE_TAG')


TG_MESSAGE_TEMPLATE = """
\U0001F4D6 <b>Sampled request</b>
<b>URL:</b>  {URL}
<b>Client IP:</b>  {ClientIP}
<b>Country:</b>  {Country}
<b>Method:</b>  {Method}
<b>HTTPVersion:</b>  {HTTPVersion}
<b>user-agent:</b>  {UserAgent}
<b>Time:</b>  {Time}
"""

user_agent = ""
host = ""


# --- rules commands ---
def rules(update, context):
    list_of_rules = [
        'AWS-AWSManagedRulesCommonRuleSet',
        'AWS-AWSManagedRulesSQLiRuleSet',
        'AWS-AWSManagedRulesLinuxRuleSet',
        'AWS-AWSManagedRulesKnownBadInputsRuleSet',
        'AWS-AWSManagedRulesAmazonIpReputationList',
        'RateLimit_base',
        'Cloudflare-Block-Request'
    ]

    button_list = []
  
    for each in list_of_rules:
        button_list.append(InlineKeyboardButton(each, callback_data=each))
  
    # n_cols = 1 is for single column and mutliple rows
    reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=1))

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Click one of these rules',
        reply_markup=reply_markup
    )


def build_menu(buttons,n_cols,header_buttons=None, footer_buttons=None):
    """
    Returns a list of inline buttons used to generate inlinekeyboard responses
    
    :param buttons: `List` of InlineKeyboardButton
    :param n_cols: Number of columns (number of list of buttons)
    :param header_buttons: First button value
    :param footer_buttons: Last button value
    :return: `List` of inline buttons
    """
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    print(menu)

    if header_buttons:
        menu.insert(0, header_buttons)

    if footer_buttons:
        menu.append(footer_buttons)
    
    return menu


# --- callback data from rules buttons ---
def handle_callback_query(update, context):
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='--- ' + update.callback_query.data + ' ---'
    )

    if re.search(r'AWS|RateLimit_base', update.callback_query.data):
        send_cloudfront_requests_data(update, context)

    if re.search(r'Cloudflare', update.callback_query.data):
        send_cloudflare_requests_data(update, context)


# --- aws cloudfront requests data ---
def get_sampled_requests_data(sample_request):
    headers_list = sample_request.get('Request').get('Headers')

    global user_agent
    global host
    for header in headers_list:
        if header.get('Name') == 'user-agent':
            user_agent = header.get('Value')
        if header.get('Name') == 'host':
            host = header.get('Value')

    sampled_requests_data = {
        'URL': 'https://' + host + sample_request.get('Request').get('URI'),
        'ClientIP': sample_request.get('Request').get('ClientIP'),
        'Country': sample_request.get('Request').get('Country'),
        'Method': sample_request.get('Request').get('Method'),
        'HTTPVersion': sample_request.get('Request').get('HTTPVersion'),
        'UserAgent': user_agent,
        'Time': sample_request.get('Timestamp').strftime("%Y-%m-%d %H:%M:%S UTC+0")
    }

    return sampled_requests_data


def get_waf_requests(rule_metric_name):
    waf = boto3.client(
        'wafv2',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='us-east-1'
    )

    start_time = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    response = waf.get_sampled_requests(
        WebAclArn='',
        RuleMetricName=rule_metric_name,
        Scope='CLOUDFRONT',
        TimeWindow={
            # 'StartTime': '2022-09-13T07:35Z',
            # 'EndTime': '2022-09-13T08:35Z'
            'StartTime': start_time,
            'EndTime': end_time
        },
        MaxItems=8
    )

    return response.get('SampledRequests')


def send_cloudfront_requests_data(update, context):
    sample_requests_list = get_waf_requests(update.callback_query.data)

    try:
        for sample_request in sample_requests_list:
            sampled_requests_data = get_sampled_requests_data(sample_request)
            sample_request_message = TG_MESSAGE_TEMPLATE.format(**sampled_requests_data)

            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=sample_request_message,
                parse_mode=telegram.ParseMode.HTML
            )
    except Exception as err:
        msg = "[ERROR] " + str(err) + " (The bot will not be able to send more than 20 messages per minute to the same group.)"
        print(msg)


# --- cloudflare requests data ---
def get_security_events_data(security_event):
    security_events_data = {
        'URL': 'https://' + security_event.get('clientRequestHTTPHost') + security_event.get('clientRequestPath'),
        'ClientIP': security_event.get('clientIP'),
        'Country': security_event.get('clientCountryName'),
        'Method': security_event.get('clientRequestHTTPMethodName'),
        'HTTPVersion': security_event.get('clientRequestHTTPProtocol'),
        'UserAgent': security_event.get('userAgent'),
        'Time': security_event.get('datetime')
    }

    return security_events_data


def get_security_events():
    url = 'https://api.cloudflare.com/client/v4/graphql/'
    headers = {'Authorization': 'Bearer ' + CLOUDFLARE_TOKEN}

    start_time = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    query = """query ListFirewallEvents($zoneTag: string, $filter: FirewallEventsAdaptiveFilter_InputObject) {
        viewer {
          zones(filter: { zoneTag: $zoneTag }) {
            firewallEventsAdaptive(
              filter: $filter
              limit: 8
              orderBy: [datetime_DESC]
            ) {
              action
              clientCountryName
              clientIP
              clientRequestHTTPMethodName
              clientRequestHTTPProtocol
              clientRequestHTTPHost
              clientRequestPath
              datetime
              userAgent
            }
          }
        }
    }"""
    variables = {
        "zoneTag": CLOUDFLARE_ZONE_TAG,
        "filter": {
            "datetime_geq": start_time,
            "datetime_leq": end_time,
            "action": "block"
        }
    }

    response = requests.post(url, headers=headers, json={'query': query , 'variables': variables})
    if response.status_code == 200:
        data = response.json()
    
    return data.get('data').get('viewer').get('zones')[0].get('firewallEventsAdaptive')


def send_cloudflare_requests_data(update, context):
    security_events_list = get_security_events()

    try:
        for security_event in security_events_list:
            security_events_data = get_security_events_data(security_event)
            security_event_message = TG_MESSAGE_TEMPLATE.format(**security_events_data)

            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=security_event_message,
                parse_mode=telegram.ParseMode.HTML
            )
    except Exception as err:
        msg = "[ERROR] " + str(err) + " (The bot will not be able to send more than 20 messages per minute to the same group.)"
        print(msg)


# --- init telegram dispatcher ---
def create_dispatcher(token):
    # Create bot, update queue and dispatcher instances
    bot = telegram.Bot(token)
    dispatcher = Dispatcher(bot, None, workers=0)

    # Register handlers
    dispatcher.add_handler(CommandHandler('rules', rules))
    dispatcher.add_handler(CallbackQueryHandler(handle_callback_query))

    return dispatcher

dispatcher = create_dispatcher(TOKEN)


# --- cloud function entry point ---
def waf_bot_webhook(request):
    update = telegram.Update.de_json(request.get_json(force=True), dispatcher.bot)

    # --- init ---
    dispatcher.process_update(update)

    return '{"status": "ok"}', 200