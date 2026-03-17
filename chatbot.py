import re

# A simple rule-based knowledge base
# We can add as many rules and languages as we need
KNOWLEDGE_BASE = {
    "en": {
        "hello": "Hello! I am a basic bot. How can I help you with reforestation today?",
        "hi": "Hello! I am a basic bot. How can I help you with reforestation today?",
        "what is this app": "This is an AI-Reforestation Planning and Monitoring System. You can analyze land, get crop recommendations, and find local help.",
        "how to start": "Go to the 'Smart Site Report' tab. You can click on the map or enter coordinates to get a full analysis of the land.",
        "carbon credits": "Carbon credits are earned by proving your reforestation project is capturing CO2. You can estimate your project's value in the 'My Carbon Projects' tab.",
        "bye": "Goodbye! Happy planting!",
        "default": "I'm sorry, I am a simple bot and don't understand that question. Please try asking about 'how to start', 'carbon credits', or 'what is this app'."
    },
    "hi": { # Hindi
        "hello": "नमस्ते! मैं एक बेसिक बॉट हूँ। मैं आज आपकी सहायता कैसे कर सकता हूँ?",
        "hi": "नमस्ते! मैं एक बेसिक बॉट हूँ। मैं आज आपकी सहायता कैसे कर सकता हूँ?",
        "namaste": "नमस्ते! मैं एक बेसिक बॉट हूँ। मैं आज आपकी सहायता कैसे कर सकता हूँ?",
        "what is this app": "यह एक एआई-संचालित वनीकरण योजना और निगरानी प्रणाली है। आप भूमि का विश्लेषण कर सकते हैं, फसल की सिफारिशें प्राप्त कर सकते हैं, और स्थानीय सहायता पा सकते हैं।",
        "how to start": "'स्मार्ट साइट रिपोर्ट' टैब पर जाएं। आप नक्शे पर क्लिक कर सकते हैं या भूमि का पूरा विश्लेषण प्राप्त करने के लिए निर्देशांक दर्ज कर सकते हैं।",
        "carbon credits": "कार्बन क्रेडिट आपके वनीकरण परियोजना द्वारा CO2 पर कब्जा करने को साबित करके अर्जित किए जाते हैं। आप 'माई कार्बन प्रोजेक्ट्स' टैब में अपने प्रोजेक्ट का मूल्य अनुमानित कर सकते हैं।",
        "bye": "अलविदा! रोपण मुबारक!",
        "default": "मुझे खेद है, मैं एक साधारण बॉट हूँ और यह सवाल नहीं समझता। कृपया 'how to start', 'carbon credits', या 'what is this app' के बारे में पूछने का प्रयास करें।"
    },
    "mr": { # Marathi
        "hello": "नमस्कार! मी एक बेसिक बॉट आहे. मी आज तुम्हाला कशी मदत करू शकतो?",
        "hi": "नमस्कार! मी एक बेसिक बॉट आहे. मी आज तुम्हाला कशी मदत करू शकतो?",
        "namaskar": "नमस्कार! मी एक बेसिक बॉट आहे. मी आज तुम्हाला कशी मदत करू शकतो?",
        "what is this app": "ही एक एआय-चालित वनीकरण नियोजन आणि देखरेख प्रणाली आहे. तुम्ही जमिनीचे विश्लेषण करू शकता, पिकांच्या शिफारसी मिळवू शकता आणि स्थानिक मदत शोधू शकता.",
        "how to start": "'स्मार्ट साइट रिपोर्ट' टॅबवर जा. तुम्ही नकाशावर क्लिक करू शकता किंवा जमिनीचे संपूर्ण विश्लेषण मिळवण्यासाठी कोऑर्डिनेट्स टाकू शकता.",
        "carbon credits": "कार्बन क्रेडिट्स तुमच्या वनीकरण प्रकल्पाने CO2 शोषून घेतल्याचे सिद्ध करून मिळवले जातात. तुम्ही 'माय कार्बन प्रोजेक्ट्स' टॅबमध्ये तुमच्या प्रकल्पाचे मूल्य अंदाजित करू शकता.",
        "bye": "पुन्हा भेटू! शुभेच्छा!",
        "default": "मला माफ करा, मी एक साधा बॉट आहे आणि मला तो प्रश्न समजत नाही. कृपया 'how to start', 'carbon credits', किंवा 'what is this app' बद्दल विचारण्याचा प्रयत्न करा."
    }
}

def get_bot_response(message: str, language: str = 'en') -> str:
    """
    Finds a simple response from the knowledge base.
    """
    message = message.lower().strip()
    
    # Get the correct language dictionary, default to English if lang not found
    lang_kb = KNOWLEDGE_BASE.get(language, KNOWLEDGE_BASE['en'])
    
    # Find a direct match
    if message in lang_kb:
        return lang_kb[message]
        
    # Find a partial match (e.g., "hello there" matches "hello")
    for key in lang_kb.keys():
        if key in message:
            return lang_kb[key]
            
    # If no match, return default
    return lang_kb.get('default', KNOWLEDGE_BASE['en']['default'])