import pytest
import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, PropertyMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.document_parser import DocumentParser

@pytest.fixture
def parser():
    config = Mock()
    config.getint.return_value = 100
    p = DocumentParser(config)
    return p

def test_parser_init(parser):
    assert parser is not None
    assert 'doc' in parser.parser_map
    assert 'docx' in parser.parser_map
    assert 'pdf' in parser.parser_map

def test_extract_text_file_not_found(parser):
    result = parser.extract_text("non_existent_file.doc")
    assert "错误: 文件不存在" in result

@patch('backend.core.document_parser.textract')
def test_parse_generic_fallback(mock_textract, parser):
    # Test generic parser calls textract
    mock_textract.process.return_value = b"parsed content"
    
    with patch('os.path.exists', return_value=True):
        # We need to bypass the extension check or use an unknown extension
        result = parser.extract_text("test.unknown_ext")
        assert "parsed content" in result
        mock_textract.process.assert_called_once()

@patch('backend.core.document_parser.win32com', None)
@patch('backend.core.document_parser.textract')
def test_parse_doc_antiword_error(mock_textract, parser):
    mock_textract.process.side_effect = Exception("Command failed with exit code 127: antiword ...")
    result = parser._parse_doc_win32("test.doc")
    assert "缺少 Microsoft Word 或 antiword 工具" in result

@patch('backend.core.document_parser.win32com', None)
@patch('backend.core.document_parser.textract')
def test_parse_doc_no_win32_fallback(mock_textract, parser):
    mock_textract.process.return_value = b"doc content"
    result = parser._parse_doc_win32("test.doc")
    assert "doc content" in result

@patch('backend.core.document_parser.win32com', None)
@patch('backend.core.document_parser.textract')
def test_parse_doc_failure(mock_textract, parser):
    mock_textract.process.side_effect = Exception("antiword failed")
    result = parser._parse_doc_win32("test.doc")
    assert "错误" in result

@patch('backend.core.document_parser.win32com')
def test_parse_doc_win32_success(mock_win32, parser):
    mock_word = Mock()
    mock_doc = Mock()
    mock_doc.Content.Text = "win32 content"
    mock_word.Documents.Open.return_value = mock_doc
    mock_win32.client.Dispatch.return_value = mock_word
    
    with patch.dict('sys.modules', {'pythoncom': Mock()}):
        with patch('os.path.abspath', return_value="C:\\test.doc"):
            result = parser._parse_doc_win32("test.doc")
            assert "win32 content" in result

@patch('backend.core.document_parser.win32com')
def test_convert_doc_to_docx(mock_win32, parser):
    mock_word = Mock()
    mock_doc = Mock()
    mock_word.Documents.Open.return_value = mock_doc
    mock_win32.client.Dispatch.return_value = mock_word
    
    # Mock _parse_docx to return content
    parser._parse_docx = Mock(return_value="converted content")
    
    with patch.dict('sys.modules', {'pythoncom': Mock()}):
        with patch('os.path.abspath', return_value="C:\\test.doc"):
            with patch('os.remove'): # Mock remove
                result = parser._convert_doc_to_docx("test.doc")
                assert result == "converted content"
                mock_doc.SaveAs2.assert_called()

@patch('backend.core.document_parser.win32com')
def test_parse_doc_win32_retry_convert(mock_win32, parser):
    mock_word = Mock()
    mock_doc_fail = Mock()
    p = PropertyMock(side_effect=Exception("COM Error"))
    type(mock_doc_fail).Content = p
    
    mock_win32.client.Dispatch.return_value = mock_word
    mock_word.Documents.Open.return_value = mock_doc_fail
    
    # Mock _convert_doc_to_docx
    parser._convert_doc_to_docx = Mock(return_value="converted content")
    
    with patch.dict('sys.modules', {'pythoncom': Mock()}):
         with patch('os.path.abspath', return_value="C:\\test.doc"):
             result = parser._parse_doc_win32("test.doc")
             assert result == "converted content"
             parser._convert_doc_to_docx.assert_called_once()

@patch('backend.core.document_parser.win32com')
@patch('backend.core.document_parser.textract')
def test_parse_doc_win32_fail_fallback_textract(mock_textract, mock_win32, parser):
    # Simulate win32com present but failing (e.g. no Word installed)
    mock_win32.client.Dispatch.side_effect = Exception("No Word")
    
    # Mock textract success
    mock_textract.process.return_value = b"textract content"
    
    with patch.dict('sys.modules', {'pythoncom': Mock()}):
        # We also need _convert_doc_to_docx to fail or return None
        # Since _convert_doc_to_docx calls Dispatch, and we mocked Dispatch to fail, it will return None
        
        result = parser._parse_doc_win32("test.doc")
        
        assert "textract content" in result
        mock_textract.process.assert_called_once()
