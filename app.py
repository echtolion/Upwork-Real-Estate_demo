import os
from flask import Flask, request, Response
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Database Configuration ---
# Use environment variable or default to 'instance/leads.db'
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'leads.db')
db_folder = os.path.dirname(db_path)
if not os.path.exists(db_folder):
    os.makedirs(db_folder) # Ensure the instance folder exists

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disable modification tracking

db = SQLAlchemy(app)

# --- Twilio Configuration (Placeholders) ---
# These will be loaded from environment variables (.env file)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER') # Your Twilio phone number

# Initialize Twilio Client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("Twilio client initialized successfully.")
    except Exception as e:
        print(f"Error initializing Twilio client: {e}")
else:
    print("Twilio credentials not found in environment variables. Skipping client initialization.")


# --- Basic Route ---
@app.route('/')
def index():
    return "AI Real Estate Lead Matching System - Prototype"

# --- Database Models ---
class Seller(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True) # Indexed for potential lookups
    asking_price = db.Column(db.Float, nullable=True) # Use Float for currency
    location = db.Column(db.String(200), nullable=True)
    # Add other relevant fields as needed, e.g., timestamp
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<Seller {self.phone_number} - Price: {self.asking_price} Loc: {self.location}>'

class Buyer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    budget = db.Column(db.Float, nullable=True)
    preferred_location = db.Column(db.String(200), nullable=True)
    # Add other relevant fields as needed
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<Buyer {self.phone_number} - Budget: {self.budget} Loc: {self.preferred_location}>'


if __name__ == '__main__':
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
    app.run(debug=True) # Run in debug mode for development


# --- Twilio Call Handling ---

@app.route('/call/initiate', methods=['GET'])
def initiate_test_call():
    """
    A simple endpoint to trigger a test call.
    Replace '+1_TARGET_PHONE_NUMBER' with a real number for testing.
    Requires ngrok or similar to expose localhost for the callback URL.
    """
    if not twilio_client:
        return "Twilio client not initialized. Check credentials.", 500
    if not TWILIO_PHONE_NUMBER:
        return "Twilio phone number not configured.", 500

    target_phone_number = "+1_TARGET_PHONE_NUMBER" # TODO: Replace with a real number for testing
    # IMPORTANT: Replace 'YOUR_NGROK_URL' with your actual ngrok forwarding URL
    # Example: http://<your-ngrok-subdomain>.ngrok.io/call/start
    callback_url = "YOUR_NGROK_URL/call/start"

    try:
        call = twilio_client.calls.create(
            to=target_phone_number,
            from_=TWILIO_PHONE_NUMBER,
            url=callback_url # Twilio will request this URL when the call connects
        )
        print(f"Call initiated with SID: {call.sid}")
        return f"Test call initiated to {target_phone_number}. SID: {call.sid}", 200
    except Exception as e:
        print(f"Error initiating call: {e}")
        return f"Error initiating call: {e}", 500

@app.route('/call/start', methods=['POST'])
def start_call():
    """
    Handles the initial phase of the call when Twilio connects.
    Returns TwiML instructions.
    """
    response = VoiceResponse()
    """
    response = VoiceResponse()
    # Use <Gather> to collect speech or DTMF input
    gather = response.gather(input='speech dtmf', action='/call/handle-initial-response', method='POST', speechTimeout='auto', numDigits=1) # Expect 1 digit for DTMF (e.g., 1 for Sell, 2 for Buy)
    gather.say("Hello! This is the AI Real Estate Lead Matching System. Are you looking to sell property, press 1. Or are you looking to buy property, press 2?")

    # If Gather completes without input, or there's an issue
    response.say("Sorry, I didn't catch that. Goodbye.")
    response.hangup()

    return Response(str(response), mimetype='text/xml')

@app.route('/call/handle-initial-response', methods=['POST'])
def handle_initial_response():
    """
    Handles the response from the initial Gather verb.
    Determines if the caller is a seller or buyer.
    """
    response = VoiceResponse()
    digits = request.values.get('Digits', None)
    speech_result = request.values.get('SpeechResult', None)
    caller_phone_number = request.values.get('From', None) # Get caller's number

    print(f"Received initial response: Digits='{digits}', Speech='{speech_result}', From='{caller_phone_number}'")

    is_seller = False
    is_buyer = False

    if digits == '1' or ('sell' in (speech_result or '').lower()):
        is_seller = True
    elif digits == '2' or ('buy' in (speech_result or '').lower() or 'purchase' in (speech_result or '').lower()):
        is_buyer = True

    if is_seller:
        gather = response.gather(input='speech', action='/call/handle-seller-location', method='POST', speechTimeout='auto')
        gather.say("Okay, you're looking to sell. What is the city and state of the property?")
        # Redirect if gather fails
        response.redirect('/call/start') # Or handle error differently
    elif is_buyer:
        gather = response.gather(input='speech', action='/call/handle-buyer-location', method='POST', speechTimeout='auto')
        gather.say("Okay, you're looking to buy. What is your preferred city and state?")
        # Redirect if gather fails
        response.redirect('/call/start') # Or handle error differently
    else:
        response.say("Sorry, I couldn't understand if you want to sell or buy. Let's try again.")
        response.redirect('/call/start') # Redirect back to the first question

    return Response(str(response), mimetype='text/xml')

@app.route('/call/handle-seller-location', methods=['POST'])
def handle_seller_location():
    """ Handles the seller's location response. """
    response = VoiceResponse()
    speech_result = request.values.get('SpeechResult', None)
    caller_phone_number = request.values.get('From', None)

    print(f"Seller Location Response: Speech='{speech_result}', From='{caller_phone_number}'")

    if speech_result:
        # Store location temporarily (e.g., in session or pass via URL params if simple)
        # For simplicity here, we'll just proceed. A real app might store state.
        location = speech_result # Basic extraction
        gather = response.gather(input='speech dtmf', action=f'/call/handle-seller-price?loc={location}', method='POST', speechTimeout='auto')
        gather.say(f"Got it. Location: {location}. What is the asking price? Please state the amount or enter it on your keypad.")
        # Redirect if gather fails
        response.say("Sorry, I didn't catch that.")
        response.hangup()
    else:
        response.say("Sorry, I didn't catch the location. Let's try again.")
        # Redirect back to ask location again or hang up
        gather = response.gather(input='speech', action='/call/handle-seller-location', method='POST', speechTimeout='auto')
        gather.say("What is the city and state of the property?")
        response.say("Sorry, I didn't catch that. Goodbye.")
        response.hangup()

    return Response(str(response), mimetype='text/xml')

@app.route('/call/handle-buyer-location', methods=['POST'])
def handle_buyer_location():
    """ Handles the buyer's location response. """
    response = VoiceResponse()
    speech_result = request.values.get('SpeechResult', None)
    caller_phone_number = request.values.get('From', None)

    print(f"Buyer Location Response: Speech='{speech_result}', From='{caller_phone_number}'")

    if speech_result:
        # Store location temporarily
        location = speech_result # Basic extraction
        gather = response.gather(input='speech dtmf', action=f'/call/handle-buyer-budget?loc={location}', method='POST', speechTimeout='auto')
        gather.say(f"Got it. Preferred location: {location}. What is your approximate budget? Please state the amount or enter it on your keypad.")
        # Redirect if gather fails
        response.say("Sorry, I didn't catch that.")
        response.hangup()
    else:
        response.say("Sorry, I didn't catch the preferred location. Let's try again.")
        # Redirect back to ask location again or hang up
        gather = response.gather(input='speech', action='/call/handle-buyer-location', method='POST', speechTimeout='auto')
        gather.say("What is your preferred city and state?")
        response.say("Sorry, I didn't catch that. Goodbye.")
        response.hangup()

    return Response(str(response), mimetype='text/xml')


# --- Final Data Handling ---

def parse_currency(input_string):
    """ Basic function to extract numbers from a string for currency. """
    if not input_string:
        return None
    try:
        # Remove common currency symbols and commas, handle potential text
        cleaned = ''.join(filter(str.isdigit or str.__eq__('.'), input_string.split()[0]))
        return float(cleaned)
    except (ValueError, IndexError):
        # Attempt to parse spoken numbers (very basic)
        # A more robust solution would use NLP libraries
        words_to_digits = {'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
                           'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'zero': '0',
                           'thousand': '000', 'million': '000000'} # Very simplified
        num_str = ""
        for word in input_string.lower().split():
            if word in words_to_digits:
                num_str += words_to_digits[word]
            elif word.isdigit():
                 num_str += word
        if num_str:
            try:
                return float(num_str)
            except ValueError:
                return None
        return None


@app.route('/call/handle-seller-price', methods=['POST'])
def handle_seller_price():
    """ Handles the seller's asking price response and saves the record. """
    response = VoiceResponse()
    digits = request.values.get('Digits', None)
    speech_result = request.values.get('SpeechResult', None)
    caller_phone_number = request.values.get('From', None)
    location = request.args.get('loc', 'Unknown') # Get location passed in URL

    print(f"Seller Price Response: Digits='{digits}', Speech='{speech_result}', From='{caller_phone_number}', Loc='{location}'")

    price_input = digits if digits else speech_result
    asking_price = parse_currency(price_input)

    if asking_price is not None and caller_phone_number:
        try:
            new_seller = Seller(
                phone_number=caller_phone_number,
                asking_price=asking_price,
                location=location
            )
            db.session.add(new_seller)
            db.session.commit()
            response.say(f"Thank you! We have recorded your property for sale in {location} with an asking price of {asking_price}. Goodbye.")
            print(f"Saved Seller: {new_seller}")
        except Exception as e:
            db.session.rollback()
            print(f"Database error saving seller: {e}")
            response.say("Sorry, there was an error saving your information. Please try again later.")
    else:
        response.say("Sorry, I couldn't understand the asking price.")
        # Optionally retry or just hang up

    response.hangup()
    return Response(str(response), mimetype='text/xml')


@app.route('/call/handle-buyer-budget', methods=['POST'])
def handle_buyer_budget():
    """ Handles the buyer's budget response and saves the record. """
    response = VoiceResponse()
    digits = request.values.get('Digits', None)
    speech_result = request.values.get('SpeechResult', None)
    caller_phone_number = request.values.get('From', None)
    location = request.args.get('loc', 'Unknown') # Get location passed in URL

    print(f"Buyer Budget Response: Digits='{digits}', Speech='{speech_result}', From='{caller_phone_number}', Loc='{location}'")

    budget_input = digits if digits else speech_result
    budget = parse_currency(budget_input)

    if budget is not None and caller_phone_number:
        try:
            new_buyer = Buyer(
                phone_number=caller_phone_number,
                budget=budget,
                preferred_location=location
            )
            db.session.add(new_buyer)
            db.session.commit()
            response.say(f"Thank you! We have recorded your interest in buying in {location} with a budget of {budget}. Goodbye.")
            print(f"Saved Buyer: {new_buyer}")
        except Exception as e:
            db.session.rollback()
            print(f"Database error saving buyer: {e}")
            response.say("Sorry, there was an error saving your information. Please try again later.")
    else:
        response.say("Sorry, I couldn't understand the budget.")
        # Optionally retry or just hang up

    response.hangup()
    return Response(str(response), mimetype='text/xml')
