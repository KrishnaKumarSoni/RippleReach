from enum import Enum

class SheetColumns(str, Enum):
    NAME = "Name"
    EMAIL = "Email"
    COMPANY_NAME = "Company Name"
    COMPANY_DOMAIN = "Company Domain"
    COMPANY_SIZE = "Company Size"
    ROLE = "Role"
    HEADLINE = "Headline"
    COMPANY_BACKGROUND = "Company Background"
    COLD_EMAIL_SUBJECT = "Cold Email Subject"
    EMAIL_CONTENT = "Email Content"
    EMAIL_STATUS = "Email Status"
    LAST_SENDER = "Last Sender"
    LAST_MESSAGE = "Last Message"
    RESPONSE = "Response"
    RESPONSE_SUBJECT = "Response Subject"
    FOLLOW_UP_NEEDED = "Follow-Up Needed"
    CONVERSATION_HISTORY = "Conversation History"
    SENDER_EMAIL = "Sender Email"
    PROPOSAL = "Proposal"
    HTML_EMAIL_CONTENT = 'HTML_EMAIL_CONTENT'

    @classmethod
    def required_columns(cls) -> list[str]:
        """List of columns that must exist in the sheet"""
        return [
            cls.NAME.value,
            cls.EMAIL.value,
            cls.COMPANY_NAME.value,
            cls.COMPANY_DOMAIN.value,
            cls.EMAIL_STATUS.value,
            cls.SENDER_EMAIL.value
        ]
    
    @classmethod
    def optional_columns(cls) -> list[str]:
        """List of columns that are optional"""
        return [col.value for col in cls if col.value not in cls.required_columns()]

    @classmethod
    def get_value(cls, field: str) -> str:
        """Get enum value with case-insensitive matching"""
        for member in cls:
            if member.value.lower() == field.lower():
                return member.value
        return field

class EmailStatus(str, Enum):
    NEW = "New"  # Initial state when lead is first added to the system
    SENT = "Sent"  # Cold email has been sent, awaiting response
    REPLIED = "Replied"  # Lead has replied to our email
    ACTIVE = "Active"  # Ongoing email conversation with the lead
    FAILED = "Failed"  # Email delivery failed or other error occurred

class SenderType(str, Enum):
    AGENCY = "Agency"
    CLIENT = "Client" 