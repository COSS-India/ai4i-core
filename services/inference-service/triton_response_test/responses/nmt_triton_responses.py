"""Triton-level stub responses for the NMT service.

These mirror the raw JSON that Triton's KServe v2 endpoint returns for an NMT
infer call.  The inference service reads ``outputs[0].data[0]`` as the
translated text.

Three sizes based on input text character length:
  SMALL_NMT_TRITON_RESPONSE   — short phrase   (< 200 chars)
  MEDIUM_NMT_TRITON_RESPONSE  — a few sentences (200–999 chars)
  LARGE_NMT_TRITON_RESPONSE   — full paragraph  (>= 1000 chars)
"""

from typing import Any

SMALL_NMT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "nmt",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": ["नमस्कार, आप कैसे हैं?"],
        }
    ],
}

MEDIUM_NMT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "nmt",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                "बैठक सोमवार की सुबह दस बजे निर्धारित की गई है। "
                "कृपया सुनिश्चित करें कि सत्र से पहले सभी आवश्यक दस्तावेज़ तैयार हों। "
                "कृपया इस संदेश का जवाब देकर अपनी उपस्थिति की पुष्टि करें।"
            ],
        }
    ],
}

LARGE_NMT_TRITON_RESPONSE: dict[str, Any] = {
    "model_name": "nmt",
    "model_version": "1",
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": [
                "कृत्रिम बुद्धिमत्ता हमारे दैनिक जीवन में प्रौद्योगिकी के साथ हमारी बातचीत के तरीके को बदल रही है। "
                "स्वास्थ्य सेवा से लेकर शिक्षा तक, AI-संचालित प्रणालियाँ पेशेवरों को तेज़ और अधिक सटीक निर्णय लेने में मदद कर रही हैं। "
                "प्राकृतिक भाषा प्रसंस्करण के क्षेत्र में, मॉडल अब सैकड़ों भाषाओं के बीच उल्लेखनीय सटीकता के साथ पाठ का अनुवाद कर सकते हैं। "
                "इसने अंतर-सांस्कृतिक संचार और वैश्विक सहयोग के लिए नई संभावनाएँ खोली हैं। "
                "दुनिया भर की सरकारें और संगठन AI अनुसंधान और विकास में भारी निवेश कर रहे हैं। "
                "हालाँकि, इन प्रगति के साथ आने वाली नैतिक चुनौतियों का समाधान करना भी उतना ही महत्वपूर्ण है, "
                "जिसमें डेटा गोपनीयता, एल्गोरिदमिक पूर्वाग्रह और रोजगार पर प्रभाव शामिल हैं।"
            ],
        }
    ],
}
