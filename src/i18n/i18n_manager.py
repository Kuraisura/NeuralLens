"""
Internationalization (i18n) and Localization (l10n) Framework
Multi-language support for Neural Lens system

Features:
- Translation management using gettext
- Language detection and switching
- Locale-aware formatting (dates, numbers, currency)
- Dynamic language loading
- Translation fallbacks
- RTL (Right-to-Left) language support

Supported Languages (initially):
- English (en_US) - Default
- Spanish (es_ES)
- French (fr_FR)
- German (de_DE)
- Japanese (ja_JP)
- Chinese Simplified (zh_CN)

Author: Neural Lens Development Team
Date: January 4, 2026
"""

import os
import gettext
import locale
from pathlib import Path
from typing import Optional, Dict, Callable, List
from datetime import datetime
from enum import Enum
import logging
import json


class Language(Enum):
    """Supported languages"""
    ENGLISH = "en_US"
    SPANISH = "es_ES"
    FRENCH = "fr_FR"
    GERMAN = "de_DE"
    JAPANESE = "ja_JP"
    CHINESE = "zh_CN"


class I18nManager:
    """
    Internationalization manager for multi-language support
    
    Directory structure:
        locales/
            en_US/
                LC_MESSAGES/
                    messages.po
                    messages.mo
            es_ES/
                LC_MESSAGES/
                    messages.po
                    messages.mo
            ...
    """
    
    # RTL (Right-to-Left) languages
    RTL_LANGUAGES = ['ar', 'he', 'fa', 'ur']
    
    def __init__(self, 
                 locales_dir: str = "locales",
                 domain: str = "messages",
                 default_language: Language = Language.ENGLISH):
        """
        Initialize i18n manager
        
        Args:
            locales_dir: Directory containing translation files
            domain: Translation domain name
            default_language: Default fallback language
        """
        self.locales_dir = Path(locales_dir)
        self.domain = domain
        self.default_language = default_language
        self.current_language = default_language
        
        # Create locales directory if it doesn't exist
        self.locales_dir.mkdir(parents=True, exist_ok=True)
        
        # Translation instances cache
        self._translations: Dict[str, gettext.GNUTranslations] = {}
        
        # Language change callbacks
        self._callbacks: List[Callable[[Language], None]] = []
        
        # Logger
        self.logger = logging.getLogger(__name__)
        
        # Load default language
        self._load_translation(self.current_language)
        
        self.logger.info(f"i18n initialized - default language: {self.current_language.value}")
    
    def _load_translation(self, language: Language) -> gettext.GNUTranslations:
        """Load translation for specified language"""
        lang_code = language.value
        
        if lang_code in self._translations:
            return self._translations[lang_code]
        
        try:
            # Try to load compiled .mo file
            translation = gettext.translation(
                self.domain,
                localedir=str(self.locales_dir),
                languages=[lang_code],
                fallback=True
            )
            
            self._translations[lang_code] = translation
            self.logger.info(f"Loaded translation: {lang_code}")
            return translation
            
        except Exception as e:
            self.logger.warning(f"Failed to load translation for {lang_code}: {e}")
            # Return NullTranslations (no-op, returns original strings)
            translation = gettext.NullTranslations()
            self._translations[lang_code] = translation
            return translation
    
    def set_language(self, language: Language):
        """
        Set current language
        
        Args:
            language: Language to switch to
        """
        if language != self.current_language:
            self.current_language = language
            self._load_translation(language)
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(language)
                except Exception as e:
                    self.logger.error(f"Language change callback failed: {e}")
            
            self.logger.info(f"Language changed to: {language.value}")
    
    def get_language(self) -> Language:
        """Get current language"""
        return self.current_language
    
    def translate(self, message: str, **kwargs) -> str:
        """
        Translate message to current language
        
        Args:
            message: Message to translate
            **kwargs: Format parameters for string interpolation
            
        Returns:
            Translated message
            
        Example:
            i18n.translate("Hello, {name}!", name="John")
        """
        translation = self._translations.get(
            self.current_language.value,
            gettext.NullTranslations()
        )
        
        translated = translation.gettext(message)
        
        # Apply string formatting if kwargs provided
        if kwargs:
            try:
                translated = translated.format(**kwargs)
            except KeyError as e:
                self.logger.warning(f"Missing format parameter: {e}")
        
        return translated
    
    def translate_plural(self, singular: str, plural: str, count: int, **kwargs) -> str:
        """
        Translate with plural forms
        
        Args:
            singular: Singular form
            plural: Plural form
            count: Count to determine plural form
            **kwargs: Format parameters
            
        Returns:
            Translated message
            
        Example:
            i18n.translate_plural("{count} item", "{count} items", count=5, count=5)
        """
        translation = self._translations.get(
            self.current_language.value,
            gettext.NullTranslations()
        )
        
        translated = translation.ngettext(singular, plural, count)
        
        # Apply string formatting
        kwargs['count'] = count
        if kwargs:
            try:
                translated = translated.format(**kwargs)
            except KeyError as e:
                self.logger.warning(f"Missing format parameter: {e}")
        
        return translated
    
    def format_date(self, dt: datetime, format_str: str = "medium") -> str:
        """
        Format date according to current locale
        
        Args:
            dt: Datetime to format
            format_str: Format style (short, medium, long, full)
            
        Returns:
            Formatted date string
        """
        try:
            # Set locale for formatting
            locale.setlocale(locale.LC_TIME, self.current_language.value)
            
            format_map = {
                "short": "%x",  # 01/04/26
                "medium": "%x %X",  # 01/04/26 14:30:00
                "long": "%A, %B %d, %Y",  # Saturday, January 04, 2026
                "full": "%A, %B %d, %Y %I:%M:%S %p"  # Saturday, January 04, 2026 02:30:00 PM
            }
            
            fmt = format_map.get(format_str, format_str)
            return dt.strftime(fmt)
            
        except Exception as e:
            self.logger.warning(f"Date formatting failed: {e}")
            return str(dt)
    
    def format_number(self, number: float, decimal_places: int = 2) -> str:
        """
        Format number according to current locale
        
        Args:
            number: Number to format
            decimal_places: Number of decimal places
            
        Returns:
            Formatted number string
        """
        try:
            locale.setlocale(locale.LC_NUMERIC, self.current_language.value)
            return locale.format_string(f"%.{decimal_places}f", number, grouping=True)
        except Exception as e:
            self.logger.warning(f"Number formatting failed: {e}")
            return f"{number:.{decimal_places}f}"
    
    def format_currency(self, amount: float, currency: str = "USD") -> str:
        """
        Format currency according to current locale
        
        Args:
            amount: Amount to format
            currency: Currency code (USD, EUR, JPY, etc.)
            
        Returns:
            Formatted currency string
        """
        try:
            locale.setlocale(locale.LC_MONETARY, self.current_language.value)
            return locale.currency(amount, symbol=True, grouping=True)
        except Exception as e:
            self.logger.warning(f"Currency formatting failed: {e}")
            return f"{currency} {amount:.2f}"
    
    def is_rtl(self) -> bool:
        """Check if current language is Right-to-Left"""
        lang_code = self.current_language.value.split('_')[0]
        return lang_code in self.RTL_LANGUAGES
    
    def get_available_languages(self) -> List[Language]:
        """Get list of available languages (that have translation files)"""
        available = [self.default_language]
        
        for language in Language:
            if language == self.default_language:
                continue
            
            lang_dir = self.locales_dir / language.value / "LC_MESSAGES"
            mo_file = lang_dir / f"{self.domain}.mo"
            
            if mo_file.exists():
                available.append(language)
        
        return available
    
    def detect_language(self) -> Language:
        """
        Detect user's preferred language from environment
        
        Returns:
            Detected language or default
        """
        try:
            # Try environment variables
            for env_var in ['LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG']:
                env_lang = os.getenv(env_var)
                if env_lang:
                    # Extract language code (e.g., "en_US.UTF-8" -> "en_US")
                    lang_code = env_lang.split('.')[0]
                    
                    # Try exact match
                    for language in Language:
                        if language.value == lang_code:
                            return language
                    
                    # Try language prefix match (e.g., "en" matches "en_US")
                    lang_prefix = lang_code.split('_')[0]
                    for language in Language:
                        if language.value.startswith(lang_prefix):
                            return language
        
        except Exception as e:
            self.logger.warning(f"Language detection failed: {e}")
        
        return self.default_language
    
    def register_callback(self, callback: Callable[[Language], None]):
        """Register callback for language changes"""
        self._callbacks.append(callback)
    
    def create_translation_template(self) -> bool:
        """
        Create POT (Portable Object Template) file from source code
        
        This scans source code for translatable strings and generates a .pot file
        that can be used to create translations for new languages.
        
        Returns:
            True if successful
        """
        try:
            pot_file = self.locales_dir / f"{self.domain}.pot"
            
            # In production, this would use xgettext or similar tool
            # For now, create a basic template
            template_content = """# Translation template for Neural Lens
# Copyright (C) 2026 Neural Lens Development Team
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"

# Common UI strings
msgid "Welcome to Neural Lens"
msgstr ""

msgid "Login"
msgstr ""

msgid "Logout"
msgstr ""

msgid "Dashboard"
msgstr ""

msgid "Attendance"
msgstr ""

msgid "Reports"
msgstr ""

msgid "Settings"
msgstr ""

msgid "Profile"
msgstr ""

# Face recognition messages
msgid "Face recognized: {name}"
msgstr ""

msgid "Face not recognized"
msgstr ""

msgid "Multiple faces detected"
msgstr ""

# Status messages
msgid "Success"
msgstr ""

msgid "Error"
msgstr ""

msgid "Warning"
msgstr ""

msgid "Please wait..."
msgstr ""

# Time-related
msgid "Today"
msgstr ""

msgid "Yesterday"
msgstr ""

msgid "This week"
msgstr ""

msgid "This month"
msgstr ""
"""
            
            pot_file.write_text(template_content)
            self.logger.info(f"Translation template created: {pot_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create translation template: {e}")
            return False


# Global i18n instance (singleton)
_i18n_instance: Optional[I18nManager] = None


def get_i18n() -> I18nManager:
    """Get global i18n instance"""
    global _i18n_instance
    if _i18n_instance is None:
        _i18n_instance = I18nManager()
    return _i18n_instance


def initialize_i18n(locales_dir: str = "locales", 
                   default_language: Language = Language.ENGLISH,
                   auto_detect: bool = True) -> I18nManager:
    """
    Initialize global i18n instance
    
    Args:
        locales_dir: Directory containing translations
        default_language: Default language
        auto_detect: Auto-detect user's language
        
    Returns:
        I18nManager instance
    """
    global _i18n_instance
    _i18n_instance = I18nManager(locales_dir, default_language=default_language)
    
    if auto_detect:
        detected_lang = _i18n_instance.detect_language()
        _i18n_instance.set_language(detected_lang)
    
    return _i18n_instance


# Convenience functions
def _(message: str, **kwargs) -> str:
    """Shorthand for translate()"""
    return get_i18n().translate(message, **kwargs)


def _n(singular: str, plural: str, count: int, **kwargs) -> str:
    """Shorthand for translate_plural()"""
    return get_i18n().translate_plural(singular, plural, count, **kwargs)
