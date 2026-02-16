#!/usr/bin/env python3
"""
Generate diverse, realistic training data for domain classification.
Creates varied examples across languages, domains, and text lengths.
"""
import pandas as pd
import random
from pathlib import Path

# Medical domain templates
MEDICAL_TEMPLATES = {
    "en": [
        "I have {symptom} and need medical attention",
        "The patient is experiencing {symptom} and requires treatment",
        "Diagnosed with {condition}, starting {treatment} immediately",
        "Severe {symptom} reported, conducting {test} now",
        "Patient complains of {symptom} since {time}",
        "Medical history shows {condition} with {complication}",
        "Prescribed {medication} for {condition} treatment",
        "Emergency case: {symptom} with {severity} intensity",
        "Follow-up appointment for {condition} management",
        "Lab results indicate {finding}, recommend {action}",
    ],
    "hi": [
        "मुझे {symptom} है और चिकित्सा सहायता चाहिए",
        "रोगी को {symptom} है और उपचार की आवश्यकता है",
        "{condition} का निदान, तुरंत {treatment} शुरू करें",
        "गंभीर {symptom} की रिपोर्ट, अब {test} कर रहे हैं",
        "रोगी को {time} से {symptom} की शिकायत है",
    ],
    "bn": [
        "আমার {symptom} আছে এবং চিকিৎসা সহায়তা প্রয়োজন",
        "রোগীর {symptom} আছে এবং চিকিৎসার প্রয়োজন",
        "{condition} নির্ণয়, অবিলম্বে {treatment} শুরু করুন",
        "গুরুতর {symptom} রিপোর্ট, এখন {test} করছি",
    ],
}

# Legal domain templates
LEGAL_TEMPLATES = {
    "en": [
        "This {document} is legally binding between {parties}",
        "The contract stipulates {clause} under {law}",
        "Legal proceedings initiated for {case} violation",
        "Agreement terms include {provision} and {obligation}",
        "Court ruling on {matter} effective {date}",
        "Compliance with {regulation} is mandatory",
        "Breach of {clause} constitutes {penalty}",
        "Legal counsel advises {action} regarding {issue}",
    ],
    "hi": [
        "यह {document} {parties} के बीच कानूनी रूप से बाध्यकारी है",
        "अनुबंध {law} के तहत {clause} निर्धारित करता है",
        "{case} उल्लंघन के लिए कानूनी कार्यवाही शुरू",
        "समझौते की शर्तों में {provision} और {obligation} शामिल हैं",
    ],
}

# Technical domain templates
TECHNICAL_TEMPLATES = {
    "en": [
        "Update the {component} configuration in {system}",
        "Deploy {version} to {environment} server",
        "Debug {error} in {module} code",
        "Optimize {algorithm} for better {metric}",
        "Implement {feature} using {technology}",
        "Refactor {code} to improve {quality}",
        "Monitor {service} performance and {metric}",
        "Configure {setting} in {application}",
    ],
    "hi": [
        "{system} में {component} कॉन्फ़िगरेशन अपडेट करें",
        "{environment} सर्वर पर {version} तैनात करें",
        "{module} कोड में {error} डीबग करें",
        "बेहतर {metric} के लिए {algorithm} अनुकूलित करें",
    ],
}

# Finance domain templates
FINANCE_TEMPLATES = {
    "en": [
        "Quarterly revenue increased by {percent} this {period}",
        "Investment portfolio shows {trend} in {sector}",
        "Financial analysis indicates {finding} for {metric}",
        "Stock price {movement} due to {factor}",
        "Budget allocation for {category} is {amount}",
        "Profit margin improved by {percent} year-over-year",
        "Market capitalization reached {value} in {period}",
        "Dividend payout of {amount} declared for {quarter}",
    ],
    "hi": [
        "तिमाही राजस्व इस {period} में {percent} बढ़ा",
        "निवेश पोर्टफोलियो {sector} में {trend} दिखाता है",
        "वित्तीय विश्लेषण {metric} के लिए {finding} इंगित करता है",
        "{factor} के कारण स्टॉक मूल्य {movement}",
    ],
}

# Casual domain templates
CASUAL_TEMPLATES = {
    "en": [
        "Hey, how are you doing today?",
        "What's up? Want to grab coffee later?",
        "Just finished watching {show}, it was amazing!",
        "Can't wait for the weekend, planning to {activity}",
        "Feeling {emotion} about {event} tomorrow",
        "Did you see {thing}? It's so {adjective}!",
        "Thinking about {topic}, what do you think?",
        "Having a great time at {place} with friends",
    ],
    "hi": [
        "अरे, आज कैसे हो?",
        "क्या हाल है? बाद में कॉफी पीने चलें?",
        "अभी {show} देखकर आया, बहुत बढ़िया था!",
        "वीकेंड का इंतजार नहीं हो रहा, {activity} करने की योजना है",
    ],
}

# General domain templates
GENERAL_TEMPLATES = {
    "en": [
        "The {topic} is important for {reason}",
        "Recent developments in {field} show {trend}",
        "According to {source}, {statement}",
        "The impact of {factor} on {outcome} is significant",
        "Research indicates {finding} in {area}",
        "Public opinion on {issue} has {change}",
        "The government announced {policy} for {sector}",
        "Climate change affects {aspect} of {system}",
    ],
    "hi": [
        "{reason} के लिए {topic} महत्वपूर्ण है",
        "{field} में हाल के विकास {trend} दिखाते हैं",
        "{source} के अनुसार, {statement}",
        "{outcome} पर {factor} का प्रभाव महत्वपूर्ण है",
    ],
}

# Vocabulary for filling templates
VOCAB = {
    "symptom": ["fever", "headache", "cough", "pain", "nausea", "fatigue", "dizziness"],
    "condition": ["diabetes", "hypertension", "asthma", "arthritis", "infection"],
    "treatment": ["medication", "therapy", "surgery", "rest", "antibiotics"],
    "test": ["blood test", "X-ray", "MRI", "CT scan", "ultrasound"],
    "time": ["yesterday", "last week", "two days", "this morning"],
    
    "document": ["contract", "agreement", "deed", "will", "lease"],
    "parties": ["both parties", "the parties", "all stakeholders"],
    "law": ["civil law", "contract law", "property law"],
    "clause": ["termination clause", "liability clause", "payment terms"],
    
    "component": ["server", "database", "API", "module", "service"],
    "system": ["production", "staging", "development"],
    "error": ["null pointer", "timeout", "connection error"],
    "technology": ["Python", "Docker", "Kubernetes", "React"],
    
    "percent": ["15%", "20%", "10%", "25%"],
    "period": ["quarter", "year", "month"],
    "sector": ["technology", "healthcare", "finance"],
    "trend": ["growth", "decline", "stability"],
}


def generate_dataset(samples_per_domain=300, samples_per_lang=50):
    """Generate diverse training dataset."""
    data = []
    
    templates_by_domain = {
        "medical": MEDICAL_TEMPLATES,
        "legal": LEGAL_TEMPLATES,
        "technical": TECHNICAL_TEMPLATES,
        "finance": FINANCE_TEMPLATES,
        "casual": CASUAL_TEMPLATES,
        "general": GENERAL_TEMPLATES,
    }
    
    for domain, lang_templates in templates_by_domain.items():
        for lang, templates in lang_templates.items():
            for _ in range(samples_per_lang):
                template = random.choice(templates)
                
                # Fill template with random vocabulary
                text = template
                for key, values in VOCAB.items():
                    if f"{{{key}}}" in text:
                        text = text.replace(f"{{{key}}}", random.choice(values))
                
                # Determine script
                if lang == "en":
                    script = "latin"
                elif lang == "hi":
                    script = "devanagari"
                elif lang == "bn":
                    script = "bengali"
                else:
                    script = "unknown"
                
                # Calculate simple complexity (will be recalculated during training)
                complexity = 0.2 + (len(text.split()) / 100) + random.uniform(-0.1, 0.1)
                complexity = max(0.1, min(0.9, complexity))
                
                data.append({
                    "text": text,
                    "language": lang,
                    "domain": domain,
                    "complexity": round(complexity, 2),
                    "source": "generated_diverse",
                    "script": script
                })
    
    return pd.DataFrame(data)


if __name__ == "__main__":
    print("Generating diverse training dataset...")
    
    # Generate dataset
    df = generate_dataset(samples_per_domain=300, samples_per_lang=100)
    
    print(f"Generated {len(df)} samples")
    print(f"\nDistribution:")
    print(df.groupby(["domain", "language"]).size())
    
    # Save
    output_path = Path("data/processed/diverse_training_data.csv")
    df.to_csv(output_path, index=False)
    print(f"\n✓ Saved to: {output_path}")

