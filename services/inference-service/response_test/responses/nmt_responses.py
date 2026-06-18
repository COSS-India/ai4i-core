"""Pre-defined NMT responses for response-size load testing.

Responses verified against the real dev instance (en → hi translation).
Each response mirrors the exact output of the NMT inference endpoint:
  "source" — original input text
  "target" — translated output text
  "smr_response" — always null

Three sizes are provided:
  SMALL_NMT_RESPONSE   — single short sentence
  MEDIUM_NMT_RESPONSE  — two to three sentences
  LARGE_NMT_RESPONSE   — full paragraph (multiple sentences)
"""

from typing import Any

SMALL_NMT_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": "Hello how are you",
            "target": "नमस्कार, आप कैसे हैं?",
        }
    ],
    "smr_response": None,
}

MEDIUM_NMT_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": (
                "The meeting has been scheduled for Monday morning at ten o'clock. "
                "Please make sure all the required documents are ready before the session. "
                "Kindly confirm your attendance by replying to this message."
            ),
            "target": (
                "बैठक सोमवार की सुबह दस बजे निर्धारित की गई है। "
                "कृपया सुनिश्चित करें कि सत्र से पहले सभी आवश्यक दस्तावेज़ तैयार हों। "
                "कृपया इस संदेश का जवाब देकर अपनी उपस्थिति की पुष्टि करें।"
            ),
        }
    ],
    "smr_response": None,
}

LARGE_NMT_RESPONSE: dict[str, Any] = {
    "output": [
        {
            "source": (
                "Artificial intelligence is transforming the way we interact with technology in our daily lives. "
                "From healthcare to education, AI-powered systems are helping professionals make faster and more accurate decisions. "
                "In the field of natural language processing, models can now translate text between hundreds of languages with remarkable accuracy. "
                "This has opened up new possibilities for cross-cultural communication and global collaboration. "
                "Governments and organizations around the world are investing heavily in AI research and development. "
                "However, it is equally important to address the ethical challenges that come with these advancements, "
                "including data privacy, algorithmic bias, and the impact on employment. "
                "A balanced approach that promotes innovation while safeguarding human rights will be essential "
                "for ensuring that AI benefits everyone equally."
            ),
            "target": (
                "कृत्रिम बुद्धिमत्ता हमारे दैनिक जीवन में प्रौद्योगिकी के साथ हमारी बातचीत के तरीके को बदल रही है। "
                "स्वास्थ्य सेवा से लेकर शिक्षा तक, AI-संचालित प्रणालियाँ पेशेवरों को तेज़ और अधिक सटीक निर्णय लेने में मदद कर रही हैं। "
                "प्राकृतिक भाषा प्रसंस्करण के क्षेत्र में, मॉडल अब सैकड़ों भाषाओं के बीच उल्लेखनीय सटीकता के साथ पाठ का अनुवाद कर सकते हैं। "
                "इसने अंतर-सांस्कृतिक संचार और वैश्विक सहयोग के लिए नई संभावनाएँ खोली हैं। "
                "दुनिया भर की सरकारें और संगठन AI अनुसंधान और विकास में भारी निवेश कर रहे हैं। "
                "हालाँकि, इन प्रगति के साथ आने वाली नैतिक चुनौतियों का समाधान करना भी उतना ही महत्वपूर्ण है, "
                "जिसमें डेटा गोपनीयता, एल्गोरिदमिक पूर्वाग्रह और रोजगार पर प्रभाव शामिल हैं। "
                "एक संतुलित दृष्टिकोण जो नवाचार को बढ़ावा देते हुए मानवाधिकारों की रक्षा करे, "
                "यह सुनिश्चित करने के लिए आवश्यक होगा कि AI सभी को समान रूप से लाभ पहुँचाए।"
            ),
        }
    ],
    "smr_response": None,
}
