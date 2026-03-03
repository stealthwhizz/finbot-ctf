"""Test invoice status validation"""

import pytest
from unittest.mock import MagicMock, patch

from finbot.tools.data.invoice import update_invoice_status, VALID_INVOICE_STATUSES
from finbot.core.auth.session import SessionContext


@pytest.mark.asyncio
async def test_update_invoice_status_validates_status():
    """Test that update_invoice_status rejects invalid status values"""
    
    # Mock session context
    mock_session = MagicMock(spec=SessionContext)
    mock_session.namespace = "test_namespace"
    mock_session.user_id = "test_user"
    
    # Test with invalid status - should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        await update_invoice_status(
            invoice_id=1,
            status="invalid_status",
            agent_notes="test notes",
            session_context=mock_session
        )
    
    assert "Invalid invoice status: 'invalid_status'" in str(exc_info.value)
    assert "Must be one of:" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_invoice_status_accepts_valid_statuses():
    """Test that update_invoice_status accepts all valid status values"""
    
    mock_session = MagicMock(spec=SessionContext)
    mock_session.namespace = "test_namespace"
    mock_session.user_id = "test_user"
    
    # Mock database objects
    mock_invoice = MagicMock()
    mock_invoice.status = "submitted"
    mock_invoice.agent_notes = "Previous notes"
    mock_invoice.to_dict.return_value = {
        "id": 1,
        "status": "processing",
        "agent_notes": "Updated notes"
    }
    
    with patch("finbot.tools.data.invoice.get_db") as mock_get_db, \
         patch("finbot.tools.data.invoice.InvoiceRepository") as mock_repo_class:
        
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        
        mock_repo = MagicMock()
        mock_repo.get_invoice.return_value = mock_invoice
        mock_repo.update_invoice.return_value = mock_invoice
        mock_repo_class.return_value = mock_repo
        
        # Test each valid status
        for valid_status in VALID_INVOICE_STATUSES:
            result = await update_invoice_status(
                invoice_id=1,
                status=valid_status,
                agent_notes=f"Testing {valid_status}",
                session_context=mock_session
            )
            
            # Should not raise ValueError
            assert result is not None
            assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_update_invoice_status_rejects_similar_invalid_statuses():
    """Test specific attack scenarios with invalid statuses"""
    
    mock_session = MagicMock(spec=SessionContext)
    mock_session.namespace = "test_namespace"
    
    invalid_statuses = [
        "cancelled",  # not in valid list
        "hacked",  # malicious attempt
        "APPROVED",  # case sensitive
        "approved ",  # whitespace
        " approved",
        "",  # empty string
        "pending",  # sounds valid but isn't
    ]
    
    for invalid_status in invalid_statuses:
        with pytest.raises(ValueError) as exc_info:
            await update_invoice_status(
                invoice_id=1,
                status=invalid_status,
                agent_notes="test",
                session_context=mock_session
            )
        
        assert "Invalid invoice status" in str(exc_info.value)
