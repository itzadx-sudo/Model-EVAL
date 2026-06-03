# Murdoch University — Information Security Policy (Synthetic Sample)

> This is a **synthetic, fabricated** policy document for prototype testing only.
> It is not an actual Murdoch University policy. It exists so the RAG knowledge
> base has something to retrieve against during the benchmark.

## ISP-01 Business Continuity and Disaster Recovery
All vendors handling University data must maintain a documented Business
Continuity Plan (BCP) and Disaster Recovery (DR) plan. Plans must be reviewed at
least annually and tested at least once every twelve months. Recovery Time
Objective (RTO) must not exceed 8 hours for systems holding University data, and
Recovery Point Objective (RPO) must not exceed 4 hours.

## ISP-02 Independent Security Assurance
Vendors must hold a current, independent security assurance report (such as SOC 2
Type II, ISO/IEC 27001 certification, or equivalent) issued within the last twelve
months. The University reserves the right to request the report under a
non-disclosure agreement.

## ISP-03 Security Standards Conformance
Vendors are expected to conform to a recognised information security standard.
ISO/IEC 27001 certification covering the production environment is the preferred
evidence of conformance. Self-attestation alone is insufficient for high-risk
systems.

## ISP-04 Architecture Documentation
Vendors must be able to provide system and network architecture diagrams on
request. Diagrams may be provided under a non-disclosure agreement and must
reflect the current production environment.

## ISP-05 Third-Party and Subprocessor Management
Vendors must perform documented risk assessments of all third parties and
subprocessors that can access University data, both at onboarding and at least
annually thereafter. Security requirements must be contractually imposed on all
subprocessors.

## ISP-06 Authentication and Access Control
Systems holding University data must enforce multi-factor authentication for all
administrative and remote access. Passwords must be a minimum of 12 characters.
Periodic forced password rotation is not required where MFA and breached-password
screening are in place.

## ISP-07 Encryption in Transit and at Rest
All University data must be encrypted in transit using TLS 1.2 or higher, with
TLS 1.3 preferred. Data at rest must be encrypted using AES-256 or equivalent.

## ISP-08 Vulnerability and Penetration Testing
Vendors must perform penetration testing of internet-facing applications at least
annually and remediate critical findings within 30 days. Evidence of the most
recent test must be available on request.

## ISP-09 Incident Response and Breach Notification
Vendors must maintain a documented incident response plan and notify the
University of any confirmed breach affecting University data within 48 hours of
confirmation. Notification must include the nature of the breach and the data
affected.

## ISP-10 Audit Logging and Retention
Vendors must retain security audit logs sufficient to investigate an incident for
a minimum of 12 months. Logs must be protected against tampering and unauthorised
deletion.
