| ID | Requirements | Type | Title | Expected |
|---|---|---|---|---|
| TC-001 | REQ-001 | positive | Verify A registered user can sign in with a valid email and passwor | A registered user can sign in with a valid email and password. |
| TC-002 | REQ-001 | negative | Reject invalid A registered user can sign in with a valid email a | An actionable validation error is displayed |
| TC-003 | REQ-002 | positive | Verify Invalid credentials show an actionable error without exposin | Invalid credentials show an actionable error without exposing account details. |
| TC-004 | REQ-002 | negative | Reject invalid Invalid credentials show an actionable error witho | An actionable validation error is displayed |
| TC-005 | REQ-003 | positive | Verify A user can sign out and cannot access a protected page after | A user can sign out and cannot access a protected page afterward. |
| TC-006 | REQ-003 | negative | Reject invalid A user can sign out and cannot access a protected  | An actionable validation error is displayed |
| TC-007 | REQ-004 | positive | Verify Repeated failed sign-ins are rate limited. | Repeated failed sign-ins are rate limited. |
| TC-008 | REQ-004 | negative | Reject invalid Repeated failed sign-ins are rate limited. | An actionable validation error is displayed |
