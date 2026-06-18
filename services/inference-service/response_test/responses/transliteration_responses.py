"""Pre-defined Transliteration responses for response-size load testing.

Responses verified against the real dev instance (en → hi transliteration).
Each response mirrors the exact output of the transliteration inference endpoint:
  "source" — original input text (English)
  "target" — transliterated output in Hindi script

Note: no "config", no "smr_response", no "taskType" field — the endpoint
excludes all three (confirmed via response_model_exclude in the route handler).

Three sizes are provided:
  SMALL_TRANSLITERATION_RESPONSE   — single short phrase
  MEDIUM_TRANSLITERATION_RESPONSE  — two to three sentences
  LARGE_TRANSLITERATION_RESPONSE   — full paragraph (multiple sentences)
"""

from typing import Any

SMALL_TRANSLITERATION_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": "Hello Good Morning",
            "target": "हेलो गुड मॉर्निंग",
        }
    ],
}

MEDIUM_TRANSLITERATION_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": (
                "My name is Ravi Kumar and I am from Mumbai Maharashtra. "
                "I work at a software company in Bangalore and I enjoy my work very much. "
                "Today the weather is very nice so I am going to the market with my family "
                "to buy some vegetables and fruits for the week."
            ),
            "target": (
                "माय नेम इज़ रवि कुमार एंड आय एम फ्रॉम मुंबई महाराष्ट्र. "
                "आय वर्क एट अ सॉफ्टवेयर कंपनी इन बैंगलोर एंड आय एन्जॉय माय वर्क वेरी मच. "
                "टुडे द वेदर इज़ वेरी नाइस सो आय एम गोइंग टू द मार्केट विद माय फैमिली "
                "टू बाय सम वेजिटेबल्स एंड फ्रूट्स फॉर द वीक."
            ),
        }
    ],
}

LARGE_TRANSLITERATION_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": (
                "India is a country with a rich cultural heritage and a diverse population. "
                "People from different states speak different languages and follow different traditions. "
                "The festivals of India are celebrated with great enthusiasm and joy across the country. "
                "Diwali, Holi, Eid, Christmas, and Pongal are some of the most popular festivals. "
                "The cuisine of India varies from region to region and is known for its rich flavors and spices. "
                "Indian classical music and dance forms like Bharatanatyam, Kathak, and Odissi have a long history. "
                "The film industry in India, commonly known as Bollywood, produces hundreds of movies every year. "
                "India has also made significant contributions to science, mathematics, and technology. "
                "The space programme of India has achieved remarkable milestones in recent years. "
                "Young people in India are increasingly interested in entrepreneurship and innovation, "
                "and many startups from India have become globally recognized companies. "
                "The education system in India continues to evolve to meet the demands of a modern economy."
            ),
            "target": (
                "इंडिया इज़ अ कंट्री विद अ रिच कल्चरल हेरिटेज एंड अ डाइवर्स पॉपुलेशन. "
                "पीपल फ्रॉम डिफरेंट स्टेट्स स्पीक डिफरेंट लैंग्वेजेस एंड फॉलो डिफरेंट ट्रेडिशन्स. "
                "द फेस्टिवल्स ऑफ इंडिया आर सेलिब्रेटेड विद ग्रेट एन्थूज़िएज्म एंड जॉय अक्रॉस द कंट्री. "
                "दिवाली, होली, ईद, क्रिसमस, एंड पोंगल आर सम ऑफ द मोस्ट पॉपुलर फेस्टिवल्स. "
                "द कुइज़ीन ऑफ इंडिया वेरीज़ फ्रॉम रीजन टू रीजन एंड इज़ नोन फॉर इट्स रिच फ्लेवर्स एंड स्पाइसेस. "
                "इंडियन क्लासिकल म्यूज़िक एंड डांस फॉर्म्स लाइक भरतनाट्यम, कथक, एंड ओडिसी हैव अ लॉन्ग हिस्ट्री. "
                "द फिल्म इंडस्ट्री इन इंडिया, कॉमनली नोन एज़ बॉलीवुड, प्रोड्यूसेस हंड्रेड्स ऑफ मूवीज़ एवरी ईयर. "
                "इंडिया हैज़ ऑल्सो मेड सिग्निफिकेंट कॉन्ट्रिब्यूशन्स टू साइंस, मैथमेटिक्स, एंड टेक्नोलॉजी. "
                "द स्पेस प्रोग्राम ऑफ इंडिया हैज़ अचीव्ड रिमार्केबल माइलस्टोन्स इन रिसेंट ईयर्स. "
                "यंग पीपल इन इंडिया आर इंक्रीसिंगली इंटरेस्टेड इन एंटरप्रेन्योरशिप एंड इनोवेशन, "
                "एंड मेनी स्टार्टअप्स फ्रॉम इंडिया हैव बिकम ग्लोबली रिकग्नाइज्ड कंपनीज़. "
                "द एजुकेशन सिस्टम इन इंडिया कंटिन्यूज़ टू इवॉल्व टू मीट द डिमांड्स ऑफ अ मॉडर्न इकॉनमी."
            ),
        }
    ],
}
