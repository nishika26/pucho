"""Simulation config — the 5 personas and their 1-week message scripts.

Four are WhatsApp end-users (driven through the router graph by
`scripts/simulate.py`); the fifth, Hema, is a dashboard expert whose "usage" is
the human-in-the-loop enrichment loop (also exercised by the simulator).

Each end-user persona carries:
    key        - short id + thread suffix
    name       - display name (the bot also learns this during onboarding)
    phone      - unique E.164 (the WhatsApp identity)
    locality   - where they live
    literacy   - seeded literacy profile: "low" | "medium" | "high"
                 (illiterate / voice-first users => "low")
    modality   - narrative label for the journey ("voice" | "text"); the
                 simulator drives the graph as text but seeds `literacy` so the
                 personalisation reflects the real channel.
    blurb      - one-line description for the printed report
    script     - list of (day, message) turns across the 7-day week

Messages are written in the language each persona actually uses (simple Hindi /
Hinglish for the low-literacy users, English for the literate ones) so the
reply-language + literacy personalisation is visible in the transcript.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    phone: str
    locality: str
    literacy: str
    modality: str
    blurb: str
    language: str = "Hindi"  # the language this persona speaks (drives --llm generation)
    script: list[tuple[int, str]] = field(default_factory=list)


JYOTSANA = Persona(
    key="jyotsana",
    name="Jyotsana",
    phone="+919900000001",
    locality="Dharavi, Mumbai",
    literacy="low",
    modality="voice",
    language="Hindi",
    blurb="42, illiterate homemaker; husband is a daily-wage worker — asking about wage rights (legal)",
    script=[
        (1, "Namaste. Mera naam Jyotsana hai. Mere pati dihaadi mazdoori karte hain."),
        (1, "Mere pati ko poora paisa nahi milta. Minimum wage kitni honi chahiye?"),
        (2, "Agar maalik kam paisa de aur time par na de, to hum kya kar sakte hain?"),
        (3, "Mazdooron ke kya haq hote hain? Hume kya milna chahiye?"),
        (5, "Zyada ghante kaam karwate hain par overtime ka paisa nahi dete. Yeh sahi hai kya?"),
        (6, "Shikayat karni ho to kahan aur kaise karein?"),
        (7, "Bahut bahut dhanyavaad. Aapne badi madad ki."),
    ],
)

MANISHA = Persona(
    key="manisha",
    name="Manisha",
    phone="+919900000002",
    locality="Parel chawl, Mumbai",
    literacy="medium",
    modality="text",
    language="Marathi",
    blurb="38, domestic worker, MA-educated; son (7) is autistic (healthcare + legal)",
    script=[
        (1, "नमस्कार, मी मनीषा. माझ्या ७ वर्षांच्या मुलाला नुकतंच ऑटिझम असल्याचं निदान झालं आहे, मला कुठून सुरुवात करावी कळत नाही."),
        (1, "माझ्या ऑटिस्टिक मुलाची काळजी कशी घ्यावी हे समजून घेण्यासाठी कोणते डॉक्टर किंवा संस्था मदत करू शकतात?"),
        (2, "दोन शाळांनी स्पष्ट कारण न देता त्याला प्रवेश नाकारला आहे. हे कायदेशीर आहे का? त्याचे हक्क काय आहेत?"),
        (3, "ऑटिस्टिक मुलांच्या थेरपी आणि शिक्षणासाठी काही सरकारी योजना किंवा एनजीओ आहेत का?"),
        (5, "मी दिवसभर ३ घरांमध्ये काम करते आणि त्याला ठेवायला कुठेही जागा नाही. डे-केअर किंवा विशेष केंद्रं आहेत का?"),
        (6, "माझ्या मुलासाठी UDID अपंगत्व प्रमाणपत्र मिळवण्यासाठी मला कोणती कागदपत्रं लागतील?"),
        (7, "अपंग मुलाला शाळा कायदेशीररीत्या प्रवेश नाकारू शकते का? लढण्यापूर्वी मला हे जाणून घ्यायचं आहे."),
    ],
)

GAURAV = Persona(
    key="gaurav",
    name="Gaurav",
    phone="+919900000003",
    locality="Matunga, Mumbai",
    literacy="medium",
    modality="text",
    language="Hinglish",
    blurb="21, commerce student — asking about scholarships for his studies (financial)",
    script=[
        (1, "Hi, mera naam Gaurav hai. Main commerce ka student hoon."),
        (1, "Mujhe apni college ki padhai ke liye scholarship chahiye. Kaun si mil sakti hai?"),
        (2, "Scholarship ke liye eligibility kya hoti hai?"),
        (4, "Mere papa ki income kam hai. Kya low-income students ke liye koi special scholarship hai?"),
        (6, "Apply kaise karun aur kaunse documents lagte hain?"),
        (7, "Thank you, isse kaafi help mili."),
    ],
)

MOHAN = Persona(
    key="mohan",
    name="Mohan",
    phone="+919900000004",
    locality="Dadar, Mumbai (migrated from Odisha)",
    literacy="low",
    modality="voice",
    language="Hinglish",
    blurb="50, illiterate street vendor, migrant — wants a driving licence (legal)",
    script=[
        (1, "Namaste. Mera naam Mohan hai. Main Dadar ke paas thele pe sabzi bechta hoon."),
        (2, "Mujhe driving licence banwana hai. Yeh kaise banega?"),
        (3, "Licence ke liye kaunse kaagaz aur documents chahiye?"),
        (5, "Main zyada padha likha nahi hoon. Kya phir bhi licence mil sakta hai?"),
        (6, "RTO office mein jaakar kya karna padta hai?"),
        (7, "Learning licence aur pakka licence mein kya farak hota hai?"),
    ],
)


# WhatsApp end-users, driven through the router graph.
WHATSAPP_PERSONAS: list[Persona] = [JYOTSANA, MANISHA, GAURAV, MOHAN]


# The fifth persona, Hema, is a dashboard EXPERT (legal), not a WhatsApp user.
# Her journey is the enrichment loop in `scripts/simulate.py::simulate_enrichment`,
# using the seeded accounts from `scripts/seed_reviewers.py`:
#   volunteer  Gaurav  <gaurav@pucho.org>  adds local context to a Q&A
#   expert     Hema    <hema@pucho.org>    enriches + approves -> ingest to KB
HEMA_EXPERT_EMAIL = "hema@pucho.org"
VOLUNTEER_EMAIL = "gaurav@pucho.org"


__all__ = [
    "Persona",
    "WHATSAPP_PERSONAS",
    "JYOTSANA",
    "MANISHA",
    "GAURAV",
    "MOHAN",
    "HEMA_EXPERT_EMAIL",
    "VOLUNTEER_EMAIL",
]
