from twilio import twiml
from twilio.rest import TwilioRestClient
from twilio import TwilioRestException
from nio.common.block.base import Block
from nio.common.discovery import Discoverable, DiscoverableType
from nio.common.versioning.dependency import DependsOn
from nio.metadata.properties.list import ListProperty
from nio.metadata.properties.expression import ExpressionProperty
from nio.metadata.properties.object import ObjectProperty
from nio.metadata.properties.string import StringProperty
from nio.modules.web import WebEngine
from nio.modules.web import RESTHandler
from nio.modules.threading import Thread
from nio.util.unique import Unique
from blocks.twilio_blocks.sms.sms_block import Recipient, TwilioCreds


class Speak(RESTHandler):

    def __init__(self, messages):
        super().__init__('/')
        self.messages = messages

    def on_post(self, identifier, body, params):
        _id = params.get('msg_id')
        phrase = twiml.Response()
        phrase.say(self.messages.get(_id, ''))
        return str(phrase)


@DependsOn("nio.modules.web", "1.0.0")
@Discoverable(DiscoverableType.block)
class TwilioVoice(Block):

    recipients = ListProperty(Recipient, title='Recipients')
    creds = ObjectProperty(TwilioCreds, title='Credentials')
    from_ = StringProperty(default='', title='From')
    url = StringProperty(default='', title='Callback URL')

    message = ExpressionProperty(
        default='An empty voice message',
        title='Message')

    def __init__(self):
        super().__init__()
        self._client = None
        self._messages = {}

    def configure(self, context):
        super().configure(context)
        self._client = TwilioRestClient(self.creds.sid,
                                        self.creds.token)
        self._server = WebEngine.create('helloworld',
                                        {'port': 8184},
                                        context)
        self._server.add_handler(Speak(self._messages))

    def process_signals(self, signals):
        for s in signals:
            self._place_calls(s)

    def _place_calls(self, signal):
        try:
            msg = self.message(signal)
            msg_id = Unique.id()
            self._messages[msg_id] = msg

            for rcp in self.recipients:
                Thread(target=self._call, args=(rcp, msg_id)).start()

        except Exception as e:
            self._logger.error(
                "Message evaluation failed: {0}: {1}".format(
                    type(e).__name__, str(e))
            )

    def _call(self, recipient, message_id, retry=False):
        try:
            # Twilio sends back some useless XML. Don't care.
            self._client.calls.create(
                to=recipient.number,
                from_=self.from_,
                url="%s?msg_id=%s" % (self.url, message_id)
            )
        except TwilioRestException as e:
            self._logger.error("Status %d" % e.status)
            if not retry:
                self._logger.debug("Retrying failed request...")
                self._call(self, recipient, message_id, True)
            else:
                raise Exception(e.msg)
        except Exception as e:
            self._logger.error("Error sending SMS to %s (%s): %s" %
                               (recipient.name, recipient.number, e))
