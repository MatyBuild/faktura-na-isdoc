"""Testy multi-provider logiky (Claude + OpenAI) — bez skutečných API volání."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# _strip_markdown
# ---------------------------------------------------------------------------

from isdoc import _strip_markdown


class TestStripMarkdown:
    def test_plain_xml(self):
        xml = '<?xml version="1.0"?><Invoice/>'
        assert _strip_markdown(xml) == xml

    def test_strips_xml_fence(self):
        raw = "```xml\n<?xml version='1.0'?><Invoice/>\n```"
        result = _strip_markdown(raw)
        assert result.startswith("<?xml")

    def test_strips_plain_fence(self):
        raw = "```\n<?xml version='1.0'?><Invoice/>\n```"
        result = _strip_markdown(raw)
        assert result.startswith("<?xml")

    def test_no_fence_unchanged(self):
        raw = "  hello  "
        assert _strip_markdown(raw) == "hello"


# ---------------------------------------------------------------------------
# extract_to_isdoc – dispatch podle providera
# ---------------------------------------------------------------------------

_DUMMY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="http://isdoc.cz/namespace/2013" version="6.0.2">
  <DocumentType>1</DocumentType>
  <ID>TEST001</ID>
  <IssueDate>2024-01-01</IssueDate>
  <TaxPointDate>2024-01-01</TaxPointDate>
  <LocalCurrencyCode>CZK</LocalCurrencyCode>
  <AccountingSupplierParty>
    <Party>
      <PostalAddress>
        <Country><IdentificationCode>CZ</IdentificationCode></Country>
      </PostalAddress>
    </Party>
  </AccountingSupplierParty>
  <PaymentMeans><Payment><PaymentMeansCode>42</PaymentMeansCode></Payment></PaymentMeans>
  <TaxTotal>
    <TaxSubTotal>
      <TaxableAmount currencyID="CZK">100.00</TaxableAmount>
      <TaxAmount currencyID="CZK">21.00</TaxAmount>
      <TaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></TaxCategory>
    </TaxSubTotal>
  </TaxTotal>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount currencyID="CZK">100.00</TaxExclusiveAmount>
    <TaxInclusiveAmount currencyID="CZK">121.00</TaxInclusiveAmount>
    <PayableAmount currencyID="CZK">121.00</PayableAmount>
  </LegalMonetaryTotal>
  <InvoiceLine>
    <ID>1</ID>
    <InvoicedQuantity unitCode="ZZ">1</InvoicedQuantity>
    <LineExtensionAmount currencyID="CZK">100.00</LineExtensionAmount>
    <Item><Description>Služba</Description></Item>
    <Price><PriceAmount currencyID="CZK">100.00</PriceAmount></Price>
    <ClassifiedTaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></ClassifiedTaxCategory>
  </InvoiceLine>
</Invoice>"""


class TestExtractToIsdocDispatch:
    def test_claude_path_called(self):
        with patch("isdoc._extract_to_isdoc_claude", return_value=_DUMMY_XML) as mock_claude, \
             patch("isdoc._extract_to_isdoc_openai") as mock_openai:
            from isdoc import extract_to_isdoc
            result = extract_to_isdoc("test text", provider="claude")
            mock_claude.assert_called_once_with("test text")
            mock_openai.assert_not_called()
            assert result == _DUMMY_XML

    def test_openai_path_called(self):
        with patch("isdoc._extract_to_isdoc_openai", return_value=_DUMMY_XML) as mock_openai, \
             patch("isdoc._extract_to_isdoc_claude") as mock_claude:
            from isdoc import extract_to_isdoc
            result = extract_to_isdoc("test text", provider="openai")
            mock_openai.assert_called_once_with("test text")
            mock_claude.assert_not_called()
            assert result == _DUMMY_XML

    def test_default_uses_env_provider(self):
        with patch("isdoc.LLM_PROVIDER", "claude"), \
             patch("isdoc._extract_to_isdoc_claude", return_value=_DUMMY_XML) as mock_claude:
            from isdoc import extract_to_isdoc
            extract_to_isdoc("test text")
            mock_claude.assert_called_once()

    def test_openai_env_provider(self):
        with patch("isdoc.LLM_PROVIDER", "openai"), \
             patch("isdoc._extract_to_isdoc_openai", return_value=_DUMMY_XML) as mock_openai:
            from isdoc import extract_to_isdoc
            extract_to_isdoc("test text")
            mock_openai.assert_called_once()


# ---------------------------------------------------------------------------
# Claude API mock
# ---------------------------------------------------------------------------

class TestClaudeApiCall:
    def test_claude_strips_fences_from_response(self):
        fenced = f"```xml\n{_DUMMY_XML}\n```"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fenced)]

        with patch("isdoc._get_anthropic") as mock_get:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get.return_value = mock_client

            from isdoc import _extract_to_isdoc_claude
            result = _extract_to_isdoc_claude("faktury text")
            assert result.startswith("<?xml")
            assert "```" not in result

    def test_claude_passes_system_prompt(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=_DUMMY_XML)]

        with patch("isdoc._get_anthropic") as mock_get:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get.return_value = mock_client

            from isdoc import _extract_to_isdoc_claude, _SYSTEM_PROMPT
            _extract_to_isdoc_claude("test")
            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs.get("system") == _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# OpenAI API mock
# ---------------------------------------------------------------------------

class TestOpenAIApiCall:
    def test_openai_strips_fences_from_response(self):
        fenced = f"```xml\n{_DUMMY_XML}\n```"
        mock_choice = MagicMock()
        mock_choice.message.content = fenced
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("isdoc._get_openai") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get.return_value = mock_client

            from isdoc import _extract_to_isdoc_openai
            result = _extract_to_isdoc_openai("faktury text")
            assert result.startswith("<?xml")
            assert "```" not in result

    def test_openai_uses_configured_model(self):
        mock_choice = MagicMock()
        mock_choice.message.content = _DUMMY_XML
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("isdoc._get_openai") as mock_get, \
             patch("isdoc.OPENAI_MODEL", "gpt-4o-mini"):
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get.return_value = mock_client

            from isdoc import _extract_to_isdoc_openai
            _extract_to_isdoc_openai("test")
            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs.kwargs.get("model") == "gpt-4o-mini"

    def test_openai_includes_system_message(self):
        mock_choice = MagicMock()
        mock_choice.message.content = _DUMMY_XML
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("isdoc._get_openai") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get.return_value = mock_client

            from isdoc import _extract_to_isdoc_openai, _SYSTEM_PROMPT
            _extract_to_isdoc_openai("test")
            call_kwargs = mock_client.chat.completions.create.call_args
            messages = call_kwargs.kwargs.get("messages", [])
            system_msgs = [m for m in messages if m.get("role") == "system"]
            assert len(system_msgs) == 1
            assert system_msgs[0]["content"] == _SYSTEM_PROMPT
