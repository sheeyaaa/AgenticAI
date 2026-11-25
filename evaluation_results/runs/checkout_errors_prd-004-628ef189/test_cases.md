| ID | Requirements | Type | Title | Expected |
|---|---|---|---|---|
| TC-001 | REQ-001 | positive | Verify A customer can submit an order with a valid delivery address | A customer can submit an order with a valid delivery address. |
| TC-002 | REQ-001 | negative | Reject invalid A customer can submit an order with a valid delive | An actionable validation error is displayed |
| TC-003 | REQ-002 | positive | Verify An expired payment method is rejected without creating an or | An expired payment method is rejected without creating an order. |
| TC-004 | REQ-002 | negative | Reject invalid An expired payment method is rejected without crea | An actionable validation error is displayed |
| TC-005 | REQ-003 | positive | Verify A service timeout shows a retry message and preserves the ca | A service timeout shows a retry message and preserves the cart. |
| TC-006 | REQ-003 | negative | Reject invalid A service timeout shows a retry message and preser | An actionable validation error is displayed |
| TC-007 | REQ-004 | positive | Verify An out-of-stock item cannot be purchased. | An out-of-stock item cannot be purchased. |
| TC-008 | REQ-004 | negative | Reject invalid An out-of-stock item cannot be purchased. | An actionable validation error is displayed |
