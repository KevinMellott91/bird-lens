"""
This sample demonstrates an implementation of the Lex Code Hook Interface
in order to serve a sample bot which manages reservations for hotel rooms and car rentals.
Bot, Intent, and Slot models which are compatible with this sample can be found in the Lex Console
as part of the 'BookTrip' template.

For instructions on how to set up and test this bot, as well as additional samples,
visit the Lex Getting Started documentation http://docs.aws.amazon.com/lex/latest/dg/getting-started.html.
"""

from __future__ import print_function
import math
import string
import random
import json
import datetime
import time
import os
import dateutil.parser
import logging
import boto3

# Provides access to s3 files.
s3 = boto3.client('s3')

# Birds that are to be viewed are in this location.
bird_queue_bucket = 'deeplens-hackathon-kevin-mellott'
bird_queue_key = 'queue/bird.jpg'

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

MAX_QUESTION = 10

#This is the welcome message for when a user starts the skill without a specific intent.
WELCOME_MESSAGE = ("Let me keep an eye on your birds!  You can ask me what birds I have seen recently and I'll show you.")
#This is the message a user will hear when they start a quiz.
SKILLTITLE = "Bird Lens"


#This is the message a user will hear when they start a quiz.
START_QUIZ_MESSAGE = "OK.  I will ask you 10 questions about the United States."

#This is the message a user will hear when they try to cancel or stop the skill"
#or when they finish a quiz.
EXIT_SKILL_MESSAGE = "I'll keep an eye out for more birds. Talk to you later!"

#This is the message a user will hear when they ask Alexa for help in your skill.
HELP_MESSAGE = ("Try saying 'what birds have you seen?'")

#If you don't want to use cards in your skill, set the USE_CARDS_FLAG to false.
#If you set it to true, you will need an image for each item in your data.
USE_CARDS_FLAG = True

STATE_START = "Start"
STATE_QUIZ = "Quiz"

STATE = STATE_START
COUNTER = 0
QUIZSCORE = 0


SAYAS_INTERJECT = "<say-as interpret-as='interjection'>"
SAYAS_SPELLOUT = "<say-as interpret-as='spell-out'>"
SAYAS = "</say-as>"
BREAKSTRONG = "<break strength='strong'/>"

 # --------------- speech cons -----------------

 # This is a list of positive/negative speechcons that this skill will use when a user
 # gets a correct answer. For a full list of supported speechcons, go here:
 # https://developer.amazon.com/public/solutions/alexa/alexa-skills-kit/docs/speechcon-reference
SPEECH_CONS_CORRECT = (["Booya", "All righty", "Bam", "Bazinga", "Bingo", "Boom", "Bravo",
                        "Cha Ching", "Cheers", "Dynomite", "Hip hip hooray", "Hurrah",
                        "Hurray", "Huzzah", "Oh dear.  Just kidding.  Hurray", "Kaboom",
                        "Kaching", "Oh snap", "Phew", "Righto", "Way to go", "Well done",
                        "Whee", "Woo hoo", "Yay", "Wowza", "Yowsa"])

SPEECH_CONS_WRONG = (["Argh", "Aw man", "Blarg", "Blast", "Boo", "Bummer", "Darn", "D'oh",
                      "Dun dun dun", "Eek", "Honk", "Le sigh", "Mamma mia", "Oh boy",
                      "Oh dear", "Oof", "Ouch", "Ruh roh", "Shucks", "Uh oh", "Wah wah",
                      "Whoops a daisy", "Yikes"])

def lambda_handler(event, context):
    """ App entry point  """

    if event['request']['type'] == "LaunchRequest":
        return on_launch()
    elif event['request']['type'] == "IntentRequest":
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'])


# --------------- response handlers -----------------

def on_intent(request, session):
    """ Called on receipt of an Intent  """

    intent = request['intent']
    intent_name = request['intent']['name']

    #print("on_intent " +intent_name)
    get_state(session)

    if 'dialogState' in request:
        #delegate to Alexa until dialog sequence is complete
        if request['dialogState'] == "STARTED" or request['dialogState'] == "IN_PROGRESS":
            return dialog_response("", False)

    # process the intents
    if intent_name == "SeenBirdIntent":
        return do_quiz(request)
    elif intent_name == "AMAZON.HelpIntent":
        return do_help()
    elif intent_name == "AMAZON.StopIntent":
        return do_stop()
    elif intent_name == "AMAZON.CancelIntent":
        return do_stop()
    elif intent_name == "AMAZON.StartOverIntent":
        return do_quiz(request)
    else:
        print("invalid intent reply with help")
        return do_help()

def answer(request, intent, session):
    """ answer a fact or quiz question """

    global STATE

    if STATE == STATE_QUIZ:
        return answer_quiz(request, intent, session)

    return answer_facts(intent)

def answer_quiz(request, intent, session):
    """ answer a quiz question  """

    global QUIZSCORE
    global COUNTER
    global STATE
    speech_message = ""
    quizprop = ""

    if session['attributes'] and 'quizitem' in session['attributes']:
        item = session['attributes']['quizitem']
    else:
        return get_welcome_message()

    if session['attributes'] and 'quizproperty' in session['attributes']:
        quizprop = session['attributes']['quizproperty']
        quizprop = quizprop.replace(" ", "").lower()

    if session['attributes'] and session['attributes']['quizscore'] != None:
        QUIZSCORE = session['attributes']['quizscore']

    if compare_slots(intent['slots'], item[quizprop]):
        QUIZSCORE += 1
        speech_message = get_speechcon(True)
    else:
        speech_message = get_speechcon(False)

    speech_message += get_answer(quizprop, item)

    if COUNTER < MAX_QUESTION:
        speech_message += get_currentscore(QUIZSCORE, COUNTER)
        return ask_question(request, speech_message)

    speech_message += get_finalscore(QUIZSCORE, COUNTER)
    speech_message += EXIT_SKILL_MESSAGE
    STATE = STATE_START
    COUNTER = 0
    QUIZSCORE = 0

    attributes = {"quizscore":globals()['QUIZSCORE'],
                  "quizproperty":quizprop,
                  "response": speech_message,
                  "state":globals()['STATE'],
                  "counter":globals()['COUNTER'],
                  "quizitem":item
                 }
    return response(attributes, response_ssml_text(speech_message, False))


def answer_facts(intent):
    """  return a fact  """

    attributes = {"state":globals()['STATE']}

    item, propname = get_item(intent.get('slots'))
    if item is None:
        speech_message = get_badanswer(propname)
        attributes.update({"response": speech_message})
        return response(attributes, response_plain_text(speech_message, False))

    speech = get_speech_description(item)
    if USE_CARDS_FLAG:
        abbrev = item.abbreviation
        cardtext = item.get_text_description()
        return response(attributes,
                        response_ssml_cardimage_prompt(propname, speech, False,
                                                       cardtext, abbrev, REPROMPT_SPEECH))
    else:
        return response(attributes,
                        response_ssml_text_reprompt
                        (speech_message, False, REPROMPT_SPEECH))


def ask_question(request, speech_message):
    # Locate the bird that is to be displayed.
    bird_image_url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bird_queue_bucket,
            'Key': bird_queue_key
        }
    )

    logger.debug(bird_image_url)

    attributes = {"state": globals()['STATE']}
    return response(attributes, response_ssml_cardimage_prompt('The Bird', 'Here is a bird', True, 'Here is a bird', bird_image_url))

def do_quiz(request):
    """ clear settings and start quiz """
    global QUIZSCORE
    global COUNTER
    global STATE

    COUNTER = 0
    QUIZSCORE = 0
    STATE = STATE_QUIZ
    return ask_question(request, "")

def do_stop():
    """  stop the app """

    attributes = {"state":globals()['STATE']}
    return response(attributes, response_plain_text(EXIT_SKILL_MESSAGE, True))

def do_help():
    """ return a help response  """

    global STATE
    STATE = STATE_START
    attributes = {"state":globals()['STATE']}
    return response(attributes, response_plain_text(HELP_MESSAGE, False))

def on_launch():
    """ called on Launch reply with a welcome message """

    return get_welcome_message()

def on_session_ended(request):
    """ called on session end  """

    if request['reason']:
        end_reason = request['reason']
        print("on_session_ended reason: " + end_reason)
    else:
        print("on_session_ended")

def get_state(session):
    """ get and set the current state  """

    global STATE

    if 'state' in session['attributes']:
        STATE = session['attributes']['state']
    else:
        STATE = STATE_START

# --------------- response string formatters -----------------
def get_welcome_message():
    """ return a welcome message """

    attributes = {"state":globals()['STATE']}
    return response(attributes, response_plain_text(WELCOME_MESSAGE, False))

# --------------- speech response handlers -----------------
#  for details of Json format see:
#  https://developer.amazon.com/public/solutions/alexa/alexa-skills-kit/docs/alexa-skills-kit-interface-reference

def response_plain_text(output, endsession):
    """ create a simple json plain text response  """

    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'shouldEndSession': endsession
    }


def response_ssml_text(output, endsession):
    """ create a simple json plain text response  """

    return {
        'outputSpeech': {
            'type': 'SSML',
            'ssml': "<speak>" +output +"</speak>"
        },
        'shouldEndSession': endsession
    }

def response_ssml_text_and_prompt(output, endsession, reprompt_text):
    """ create a Ssml response with prompt  """

    return {
        'outputSpeech': {
            'type': 'SSML',
            'ssml': "<speak>" +output +"</speak>"
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'SSML',
                'ssml': "<speak>" +reprompt_text +"</speak>"
            }
        },
        'shouldEndSession': endsession
    }


def response_ssml_cardimage_prompt(title, output, endsession, cardtext, imageUrl):
    """ create a simple json plain text response  """

    return {
        'card': {
            'type': 'Standard',
            'title': title,
            'text': cardtext,
            'image':{
                'smallimageurl':imageUrl,
                'largeimageurl':imageUrl
            },
        },
        'outputSpeech': {
            'type': 'SSML',
            'ssml': "<speak>" +output +"</speak>"
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'SSML',
                'ssml': "<speak>" +output +"</speak>"
            }
        },
        'directives': [
          {
            'type': 'Display.RenderTemplate',
            'template': {
              'type': 'BodyTemplate7',
              'token': 'SampleTemplate_3476',
              'backButton': 'VISIBLE',
              'title': 'Bird Lens',
              'backgroundImage': {
                'contentDescription': 'Textured grey background',
                'sources': [
                  {
                    'url': imageUrl
                  }
                ]
              }#,
              # 'image': {
              #   'contentDescription': 'Mount St. Helens landscape',
              #   'sources': [
              #     {
              #       'url': imageUrl
              #     }
              #   ]
              # }
            }
          },
          {
            'type': 'Hint',
            'hint': {
              'type': 'PlainText',
              'text': 'string'
            }
          }
        ],
        'shouldEndSession': endsession
    }

def response_ssml_text_reprompt(output, endsession, reprompt_text):
    """  create a simple json response with a card  """

    return {
        'outputSpeech': {
            'type': 'SSML',
            'ssml': "<speak>" +output +"</speak>"
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'SSML',
                'ssml': "<speak>" +reprompt_text +"</speak>"
            }
        },
        'shouldEndSession': endsession
    }

def dialog_response(attributes, endsession):
    """  create a simple json response with card """

    return {
        'version': '1.0',
        'sessionAttributes': attributes,
        'response':{
            'directives': [
                {
                    'type': 'Dialog.Delegate'
                }
            ],
            'shouldEndSession': endsession
        }
    }

def response(attributes, speech_response):
    """ create a simple json response """

    return {
        'version': '1.0',
        'sessionAttributes': attributes,
        'response': speech_response
    }
