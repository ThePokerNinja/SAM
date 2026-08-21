# Agent Skills — Voice Agent Appointment Skill

## 1. Purpose

This document defines the **Voice Agent Appointment Skill** for the `Agent Skills` project.

The skill enables a voice agent to schedule, confirm, manage, conduct, follow up on, and learn from appointments across enterprise, SMB, and consumer appointment workflows.

The goal is not only to book appointments, but to improve the probability that appointments are attended, completed successfully, and converted into a next useful action.

---

## 2. Core Use Cases

### 2.1 Enterprise / Business Meetings

Primary examples:

- Sales discovery calls
- Customer success calls
- Product demos
- Internal stakeholder meetings
- Consulting calls
- Recruiting screens
- Support escalations

Supported meeting platforms:

- Zoom
- Google Meet
- Microsoft Teams
- Webex
- Phone call fallback

Important correction to the original assumption:

> Zoom and Google Meet are important, but enterprise appointment workflows should also include Microsoft Teams as a first-class integration. In many enterprise environments, Teams may be as important as Zoom or Google Meet.

### 2.2 SMB / Service Provider Appointments

Primary examples:

- Doctors
- Chiropractors
- Dentists
- Spas
- Salons
- Nail appointments
- Massage appointments
- Wine tastings
- Local service providers
- Fitness trainers
- Consultants

These workflows often require:

- Availability lookup
- Service selection
- Staff/provider selection
- Location selection
- Intake questions
- Deposit or payment support
- Reminder automation
- No-show reduction

### 2.3 Consumer / Personal Appointments

Primary examples:

- Dentist
- Doctor
- Eye exam
- Mechanic
- Vet appointment
- Personal service booking

This category may have lower direct demand as a standalone business model, but is still useful as a universal capability inside a general-purpose personal agent.

---

## 3. Skill Objective

The appointment skill should support the complete lifecycle:

```text
Intent → Qualification → Availability → Booking → Confirmation → Reminder → Attendance → Meeting Execution → Follow-up → Rebooking → Learning
```

The skill should optimize for:

1. More appointments booked
2. More appointments attended
3. More appointments completed successfully
4. More second appointments or follow-up actions booked
5. Lower no-show rate
6. Lower manual scheduling work
7. Better caller/customer experience

---

## 4. Primary Performance KPI

The top-level KPI is not only whether an appointment was booked.

The highest-value KPI is:

```text
Successful Rebooking Rate
```

Because the user specifically defined that a second appointment or follow-up meeting is the strongest signal that the appointment workflow created real value.

### 4.1 KPI Priority Order

```text
1. Successful Rebooking Rate
2. Appointment Attendance Rate
3. Appointment Booking Conversion Rate
4. Appointment Completion Rate
5. No-Show Reduction
6. Time-to-Book
7. Caller Satisfaction
8. Agent Confidence / Self-Assessment
```

---

## 5. Appointment Lifecycle Workflow

## 5.1 Entry Point

A user may enter the appointment workflow through:

- Inbound phone call
- Missed call callback
- Website “Book Appointment” button
- Website “Call Now” button
- SMS conversation
- Email request
- CRM lead handoff
- Calendar link
- Voice agent conversation
- Existing customer rebooking prompt

The agent must identify scheduling intent.

### Scheduling Intent Examples

```text
“I want to book a call.”
“Can I schedule an appointment?”
“Do you have anything tomorrow?”
“I need to reschedule.”
“Can someone call me back?”
“I want to come in for a consultation.”
“Book me with Dr. Smith.”
“Do you have anything this Friday afternoon?”
```

---

## 5.2 Identity and Contact Capture

The agent should capture or infer:

- Full name
- Phone number
- Email address
- Preferred communication channel
- Time zone
- Existing customer status
- CRM/contact ID if available
- Consent for SMS/email reminders
- Consent for calendar invite
- Consent for call recording if applicable

### Contact Capture Rule

The agent should avoid making the user repeat information that is already known.

Priority order:

```text
1. CRM profile
2. Authenticated account profile
3. Previous conversation/session memory
4. Caller ID / phone metadata
5. Browser/session context
6. User-provided input
```

---

## 5.3 Appointment Qualification

The agent should collect context needed to book the correct appointment.

### Universal Qualification Fields

```yaml
appointment_type: string
reason_for_visit_or_call: string
preferred_date: date | null
preferred_time_window: string | null
time_zone: string
duration_minutes: integer
location_type: enum
priority: enum
required_attendees: array
notes: string
```

### `location_type` Options

```yaml
location_type:
  - phone_call
  - zoom
  - google_meet
  - microsoft_teams
  - webex
  - in_person
  - custom_url
```

---

## 5.4 Availability Calculation

The agent should calculate available appointment slots by combining:

```text
Provider calendar availability
+ Business hours
+ Appointment duration
+ Buffer time
+ Travel/location constraints
+ Staff/resource constraints
+ User preference
+ Time zone
+ Existing holds
+ Cancellation/no-show prediction
```

### Slot Eligibility Formula

Each candidate slot must pass:

```text
SlotEligible = CalendarFree
             AND WithinBusinessHours
             AND ResourceAvailable
             AND MeetsDuration
             AND MeetsBufferRules
             AND MeetsUserConstraints
             AND NotBlockedByPolicy
```

A slot is only shown if:

```text
SlotEligible = true
```

---

## 5.5 Slot Ranking Formula

If multiple valid slots exist, the agent should rank them.

### Slot Score

```text
SlotScore =
  (PreferenceMatch × 0.35)
+ (AttendanceProbability × 0.30)
+ (BusinessPriority × 0.20)
+ (ScheduleEfficiency × 0.15)
```

Where each value is normalized from `0.0` to `1.0`.

### Definitions

```text
PreferenceMatch:
How closely the slot matches the user’s requested date/time.

AttendanceProbability:
Predicted likelihood that the user will attend this appointment.

BusinessPriority:
How valuable the appointment is to the business.

ScheduleEfficiency:
How well the slot fits the provider’s schedule without creating gaps, conflicts, or inefficient fragmentation.
```

### Recommended Rule

The agent should offer the top 2–3 ranked slots, not an overwhelming list.

---

## 5.6 Booking Confirmation

Once a slot is selected, the agent creates an appointment object and sends confirmations.

Confirmation channels:

- SMS
- Email
- Calendar invite
- CRM record
- Optional internal notification

### Confirmation Message Must Include

```text
Appointment date
Appointment time
Time zone
Appointment type
Meeting location or link
Provider/host
Reschedule link or instruction
Cancellation policy if applicable
Preparation instructions if applicable
```

---

## 5.7 Reminder Workflow

The agent should schedule reminders.

Default reminder cadence:

```text
T - 24 hours: reminder
T - 2 hours: reminder
T - 15 minutes: final reminder
```

For high no-show-risk users, increase reminder intensity.

### Dynamic Reminder Formula

```text
ReminderIntensity =
  BaseReminderLevel
+ NoShowRiskAdjustment
+ AppointmentValueAdjustment
+ FirstTimeCustomerAdjustment
```

Example:

```text
If NoShowRisk > 0.70:
  Add extra reminder at T - 4 hours
  Ask user to confirm attendance
```

---

## 5.8 Attendance Tracking

The agent must verify whether the appointment happened.

Attendance can be inferred from:

- Zoom/Meet/Teams attendance logs
- Telephony call connection status
- Calendar event status
- CRM event completion
- Agent meeting notes
- Human confirmation
- Follow-up interaction

### Attendance States

```yaml
attendance_status:
  - attended
  - no_show
  - cancelled
  - rescheduled
  - incomplete
  - unknown
```

---

## 5.9 Meeting Execution

If the voice agent conducts or moderates the appointment, it should:

- Start on time
- Confirm identity
- Confirm purpose
- Follow the correct script/playbook
- Adapt based on user responses
- Keep the meeting on track
- Capture notes
- Identify action items
- Identify objections or unresolved questions
- Track sentiment
- Track outcome
- Ask for or schedule next step

---

## 5.10 Post-Meeting Follow-Up

After the meeting, the agent should send:

- Summary
- Notes
- Action items
- Next steps
- Relevant links
- Billing/payment instructions if needed
- Next appointment confirmation if booked

The agent should also update:

- CRM
- Calendar
- Contact profile
- Appointment record
- Performance analytics
- Skill learning log

---

# 6. Data Objects and Schema

## 6.1 Contact Object

```json
{
  "contact_id": "string",
  "full_name": "string",
  "phone": "string",
  "email": "string",
  "preferred_channel": "sms | email | phone | voice | unknown",
  "time_zone": "string",
  "crm_id": "string | null",
  "existing_customer": true,
  "consent_sms": true,
  "consent_email": true,
  "consent_recording": false,
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

## 6.2 Appointment Object

```json
{
  "appointment_id": "string",
  "contact_id": "string",
  "appointment_type": "string",
  "status": "requested | booked | confirmed | reminded | attended | no_show | cancelled | rescheduled | completed",
  "start_time": "datetime",
  "end_time": "datetime",
  "time_zone": "string",
  "duration_minutes": 30,
  "location_type": "phone_call | zoom | google_meet | microsoft_teams | webex | in_person | custom_url",
  "location_value": "string",
  "host_user_id": "string",
  "required_attendees": ["string"],
  "calendar_event_id": "string | null",
  "crm_record_id": "string | null",
  "meeting_platform_event_id": "string | null",
  "source_channel": "phone | sms | web | email | crm | calendar | voice_agent",
  "booking_confidence": 0.0,
  "attendance_probability": 0.0,
  "no_show_risk": 0.0,
  "rebooking_probability": 0.0,
  "notes": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

## 6.3 Slot Object

```json
{
  "slot_id": "string",
  "start_time": "datetime",
  "end_time": "datetime",
  "time_zone": "string",
  "host_user_id": "string",
  "resource_id": "string | null",
  "is_available": true,
  "preference_match": 0.0,
  "attendance_probability": 0.0,
  "business_priority": 0.0,
  "schedule_efficiency": 0.0,
  "slot_score": 0.0
}
```

---

## 6.4 Reminder Object

```json
{
  "reminder_id": "string",
  "appointment_id": "string",
  "channel": "sms | email | phone | push",
  "scheduled_time": "datetime",
  "sent_time": "datetime | null",
  "status": "scheduled | sent | failed | cancelled",
  "message_template_id": "string",
  "response_received": true,
  "response_value": "confirmed | cancelled | reschedule_requested | unknown"
}
```

---

## 6.5 Meeting Outcome Object

```json
{
  "meeting_outcome_id": "string",
  "appointment_id": "string",
  "attendance_status": "attended | no_show | cancelled | rescheduled | incomplete | unknown",
  "meeting_completed": true,
  "outcome_type": "qualified | not_qualified | sold | follow_up_needed | support_resolved | unresolved | unknown",
  "next_step_required": true,
  "next_appointment_booked": false,
  "billing_action_required": false,
  "summary": "string",
  "action_items": ["string"],
  "caller_sentiment_score": 0.0,
  "agent_performance_score": 0.0,
  "created_at": "datetime"
}
```

---

## 6.6 Skill Learning Log Object

```json
{
  "learning_log_id": "string",
  "period_start": "date",
  "period_end": "date",
  "metric_name": "string",
  "baseline_value": 0.0,
  "current_value": 0.0,
  "delta": 0.0,
  "trend_direction": "up | down | flat",
  "detected_problem": "string",
  "proposed_skill_candidate_id": "string | null",
  "created_at": "datetime"
}
```

---

# 7. Performance Metrics

## 7.1 Booking Conversion Rate

Measures how often scheduling intent becomes a booked appointment.

```text
BookingConversionRate =
  BookedAppointments / SchedulingIntentSessions
```

Example:

```text
80 booked appointments / 100 scheduling sessions = 0.80 or 80%
```

---

## 7.2 Attendance Rate

Measures whether booked appointments actually happen.

```text
AttendanceRate =
  AttendedAppointments / BookedAppointments
```

---

## 7.3 No-Show Rate

```text
NoShowRate =
  NoShowAppointments / BookedAppointments
```

---

## 7.4 Completion Rate

Measures whether the appointment reached a valid outcome.

```text
CompletionRate =
  CompletedAppointments / AttendedAppointments
```

---

## 7.5 Rebooking Rate

Measures whether a follow-up appointment was booked.

```text
RebookingRate =
  FollowUpAppointmentsBooked / CompletedAppointments
```

---

## 7.6 Successful Rebooking Rate

This is the highest-priority KPI.

```text
SuccessfulRebookingRate =
  FollowUpAppointmentsAttended / CompletedAppointments
```

This is stronger than simply booking the next meeting because it proves the next meeting actually happened.

---

## 7.7 Time-to-Book

Measures friction in the booking flow.

```text
TimeToBook =
  BookingConfirmedTimestamp - SchedulingIntentDetectedTimestamp
```

---

## 7.8 Reminder Confirmation Rate

```text
ReminderConfirmationRate =
  ConfirmedReminderResponses / ReminderMessagesSent
```

---

## 7.9 Reschedule Recovery Rate

Measures how well the agent saves appointments that might otherwise be lost.

```text
RescheduleRecoveryRate =
  RescheduledAppointmentsAttended / RescheduleRequests
```

---

# 8. Prediction Models

## 8.1 Attendance Probability

The system should estimate whether the user is likely to attend.

```text
AttendanceProbability =
  sigmoid(
    β0
  + β1 × PriorAttendanceRate
  + β2 × ReminderConfirmed
  + β3 × TimeUntilAppointment
  + β4 × AppointmentValue
  + β5 × SourceChannelQuality
  + β6 × CalendarInviteAccepted
  + β7 × FirstTimeCustomerPenalty
  )
```

### Practical Simple Version

If no ML model exists yet:

```text
AttendanceProbability =
  (PriorAttendanceScore × 0.25)
+ (ReminderConfirmationScore × 0.25)
+ (CalendarAcceptanceScore × 0.20)
+ (SourceQualityScore × 0.15)
+ (TimeFitScore × 0.15)
```

---

## 8.2 No-Show Risk

```text
NoShowRisk = 1 - AttendanceProbability
```

---

## 8.3 Rebooking Probability

```text
RebookingProbability =
  (MeetingCompletionScore × 0.30)
+ (CallerSatisfactionScore × 0.25)
+ (NeedForFollowUpScore × 0.20)
+ (OfferClarityScore × 0.15)
+ (TimingFitScore × 0.10)
```

---

# 9. Voice Agent Appointment Performance Score

After each appointment workflow, the agent should evaluate its own appointment performance.

## 9.1 Appointment Performance Score

```text
AppointmentPerformanceScore =
  (BookingSuccessScore × 0.25)
+ (AttendanceSuccessScore × 0.25)
+ (CallerSatisfactionScore × 0.20)
+ (MeetingOutcomeScore × 0.20)
+ (FollowUpSuccessScore × 0.10)
```

---

## 9.2 Score Definitions

### Booking Success Score

```text
1.0 = appointment booked correctly
0.5 = appointment partially booked or required manual intervention
0.0 = appointment not booked
```

### Attendance Success Score

```text
1.0 = appointment attended
0.5 = appointment rescheduled
0.0 = no-show or failed attendance
```

### Caller Satisfaction Score

Can be explicit or inferred.

```text
ExplicitScore = UserRating / MaxRating
```

Example:

```text
4 out of 5 = 0.80
```

Inferred sentiment may use:

```text
tone
frustration
interruptions
repeat questions
call ending sentiment
positive/negative language
```

### Meeting Outcome Score

```text
1.0 = clear successful outcome
0.7 = useful but incomplete outcome
0.4 = unclear outcome
0.0 = failed outcome
```

### Follow-Up Success Score

```text
1.0 = next appointment booked
0.7 = next action accepted
0.4 = follow-up sent but not accepted
0.0 = no follow-up
```

---

# 10. Weekly Learning Loop

Every week, the agent should review appointment performance and propose improvements.

## 10.1 Weekly Evaluation Inputs

```text
BookingConversionRate
AttendanceRate
NoShowRate
CompletionRate
RebookingRate
SuccessfulRebookingRate
TimeToBook
ReminderConfirmationRate
RescheduleRecoveryRate
CallerSatisfactionScore
AgentSelfAssessmentScore
```

---

## 10.2 Metric Delta

```text
MetricDelta =
  CurrentPeriodMetric - PreviousPeriodMetric
```

---

## 10.3 Percent Change

```text
PercentChange =
  (CurrentPeriodMetric - PreviousPeriodMetric) / PreviousPeriodMetric
```

---

## 10.4 Trend Detection

```text
TrendScore =
  (CurrentMetric - RollingAverageMetric) / RollingStandardDeviation
```

This helps identify meaningful outliers.

Example:

```text
If TrendScore > 2.0:
  Positive outlier

If TrendScore < -2.0:
  Negative outlier
```

---

# 11. Skill Candidate Generation

The agent should propose new skill candidates when it detects recurring friction.

## 11.1 Candidate Trigger Examples

### Low Booking Conversion

Possible skill candidate:

```text
Better slot negotiation skill
```

### High No-Show Rate

Possible skill candidate:

```text
Adaptive reminder skill
```

### Low Rebooking Rate

Possible skill candidate:

```text
Next-step recommendation skill
```

### High Time-to-Book

Possible skill candidate:

```text
Fast-booking shortcut skill
```

### Low Caller Satisfaction

Possible skill candidate:

```text
Empathy and clarification skill
```

### High Reschedule Requests

Possible skill candidate:

```text
Smart rescheduling skill
```

---

# 12. Skill Adoption Scoring Model

New appointment-related skills should not be automatically adopted.

They enter a candidate queue and must pass a weighted scoring model.

## 12.1 Evaluation Categories

```text
Impact: 50%
Strategic Alignment: 25%
Risk Assessment: 15%
Urgency / Urgency Trend: 10%
```

---

## 12.2 Skill Adoption Score

```text
SkillAdoptionScore =
  (ImpactScore × 0.50)
+ (StrategicAlignmentScore × 0.25)
+ (RiskAdjustedScore × 0.15)
+ (UrgencyTrendScore × 0.10)
```

All scores are normalized from `0.0` to `1.0`.

---

## 12.3 Impact Score

Impact measures expected improvement to core KPIs.

```text
ImpactScore =
  (ExpectedRebookingLift × 0.35)
+ (ExpectedAttendanceLift × 0.25)
+ (ExpectedBookingConversionLift × 0.20)
+ (ExpectedNoShowReduction × 0.10)
+ (ExpectedOperationalSavings × 0.10)
```

### Example

```text
ExpectedRebookingLift = 0.80
ExpectedAttendanceLift = 0.70
ExpectedBookingConversionLift = 0.60
ExpectedNoShowReduction = 0.50
ExpectedOperationalSavings = 0.40

ImpactScore =
  (0.80 × 0.35)
+ (0.70 × 0.25)
+ (0.60 × 0.20)
+ (0.50 × 0.10)
+ (0.40 × 0.10)

ImpactScore = 0.665
```

---

## 12.4 Strategic Alignment Score

Strategic alignment combines:

- Fit with product strategy
- Fit with appointment workflow
- Technical feasibility
- Integration feasibility
- Reuse across use cases

```text
StrategicAlignmentScore =
  (ProductFit × 0.30)
+ (WorkflowFit × 0.25)
+ (TechnicalFeasibility × 0.20)
+ (IntegrationFeasibility × 0.15)
+ (ReusePotential × 0.10)
```

---

## 12.5 Risk-Adjusted Score

Risk is inverted because lower risk is better.

```text
RiskAdjustedScore = 1 - RawRiskScore
```

Raw risk is calculated as:

```text
RawRiskScore =
  (LiabilityRisk × 0.25)
+ (DataPrivacyRisk × 0.20)
+ (PlatformStabilityRisk × 0.20)
+ (PerformanceRisk × 0.15)
+ (DependencyRisk × 0.10)
+ (ImplementationCostRisk × 0.10)
```

### Risk Interpretation

```text
0.0 = no risk
0.5 = moderate risk
1.0 = severe risk
```

Because the adoption formula uses `RiskAdjustedScore`, low risk improves the final score.

---

## 12.6 Urgency Trend Score

Urgency is not primarily a static measure.

The important signal is whether urgency is increasing as an outlier relative to historical norms.

```text
UrgencyTrendScore =
  clamp(
    0.5 + ((CurrentUrgency - RollingAverageUrgency) / RollingStandardDeviation) × 0.1,
    0,
    1
  )
```

If no historical data exists:

```text
UrgencyTrendScore = StaticUrgencyScore
```

---

# 13. Barrier to Entry

A skill candidate must meet all three gates.

## 13.1 Gate 1 — Minimum Score

```text
SkillAdoptionScore >= 0.80
```

Equivalent:

```text
80% or higher
```

---

## 13.2 Gate 2 — Risk Ceiling

Even if the total score is high, the skill should be blocked if risk is too high.

```text
RawRiskScore <= 0.40
```

If:

```text
RawRiskScore > 0.40
```

Then the skill remains queued or requires human review.

---

## 13.3 Gate 3 — Strategic Alignment Floor

The skill must fit the platform strategy.

```text
StrategicAlignmentScore >= 0.70
```

---

## 13.4 Final Adoption Rule

```text
AdoptSkill =
  SkillAdoptionScore >= 0.80
  AND RawRiskScore <= 0.40
  AND StrategicAlignmentScore >= 0.70
```

---

# 14. Skill Queue States

```yaml
skill_candidate_status:
  - proposed
  - queued
  - under_review
  - approved
  - rejected
  - deferred
  - needs_more_data
  - implemented
  - retired
```

---

# 15. Skill Candidate Object

```json
{
  "skill_candidate_id": "string",
  "name": "string",
  "description": "string",
  "trigger_metric": "string",
  "detected_problem": "string",
  "expected_kpi_lift": {
    "rebooking_lift": 0.0,
    "attendance_lift": 0.0,
    "booking_conversion_lift": 0.0,
    "no_show_reduction": 0.0,
    "operational_savings": 0.0
  },
  "scores": {
    "impact_score": 0.0,
    "strategic_alignment_score": 0.0,
    "raw_risk_score": 0.0,
    "risk_adjusted_score": 0.0,
    "urgency_trend_score": 0.0,
    "skill_adoption_score": 0.0
  },
  "gates": {
    "meets_score_threshold": false,
    "meets_risk_threshold": false,
    "meets_alignment_threshold": false,
    "approved_for_adoption": false
  },
  "status": "queued",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

# 16. Required Integrations

## 16.1 Calendar

Required:

- Google Calendar
- Microsoft Outlook Calendar

Optional:

- Apple Calendar via ICS
- CalDAV

## 16.2 Meeting Platforms

Required:

- Zoom
- Google Meet
- Microsoft Teams

Optional:

- Webex
- Custom meeting URL

## 16.3 Messaging

Already assumed available:

- SMS

Recommended:

- Email
- Calendar invite
- Optional push notification

## 16.4 CRM

Recommended:

- Salesforce
- HubSpot
- Zoho
- Pipedrive
- Custom CRM webhook

## 16.5 Data Import / Export

Required:

- CSV import
- CSV export

Recommended:

- Webhook event export
- JSON API
- Audit log export

---

# 17. Security, Consent, and Compliance

The agent must track consent and avoid silent data access.

## 17.1 Consent Requirements

The agent should explicitly capture consent for:

- SMS reminders
- Email reminders
- Calendar invitations
- Call recording
- CRM data storage
- Meeting transcription
- AI-generated summaries

## 17.2 Security Requirements

```text
Use OAuth where possible.
Do not store raw API keys unnecessarily.
Encrypt tokens at rest.
Log all calendar write actions.
Provide user-visible confirmation before final booking.
Support cancellation and deletion workflows.
Respect role-based permissions.
Avoid double-booking.
```

---

# 18. Implementation Pseudocode

```python
def handle_scheduling_intent(session):
    contact = resolve_or_create_contact(session)
    appointment_request = collect_appointment_requirements(session, contact)

    candidate_slots = find_candidate_slots(appointment_request)
    eligible_slots = [slot for slot in candidate_slots if is_slot_eligible(slot)]

    ranked_slots = rank_slots(eligible_slots)
    selected_slot = negotiate_slot_with_user(ranked_slots, session)

    appointment = create_appointment(contact, appointment_request, selected_slot)

    send_confirmation(appointment)
    schedule_reminders(appointment)

    log_booking_event(appointment)

    return appointment
```

```python
def evaluate_appointment_outcome(appointment):
    outcome = determine_attendance_and_completion(appointment)

    scores = {
        "booking_success": score_booking_success(appointment),
        "attendance_success": score_attendance(outcome),
        "caller_satisfaction": score_caller_satisfaction(appointment),
        "meeting_outcome": score_meeting_outcome(outcome),
        "follow_up_success": score_follow_up(outcome)
    }

    appointment_performance_score = (
        scores["booking_success"] * 0.25
        + scores["attendance_success"] * 0.25
        + scores["caller_satisfaction"] * 0.20
        + scores["meeting_outcome"] * 0.20
        + scores["follow_up_success"] * 0.10
    )

    store_performance_score(appointment, appointment_performance_score)
    return appointment_performance_score
```

```python
def evaluate_skill_candidate(candidate):
    impact = calculate_impact_score(candidate)
    alignment = calculate_strategic_alignment_score(candidate)
    raw_risk = calculate_raw_risk_score(candidate)
    risk_adjusted = 1 - raw_risk
    urgency = calculate_urgency_trend_score(candidate)

    adoption_score = (
        impact * 0.50
        + alignment * 0.25
        + risk_adjusted * 0.15
        + urgency * 0.10
    )

    approved = (
        adoption_score >= 0.80
        and raw_risk <= 0.40
        and alignment >= 0.70
    )

    return {
        "skill_adoption_score": adoption_score,
        "approved_for_adoption": approved
    }
```

---

# 19. End-to-End Learning Loop

```text
1. Agent receives scheduling intent.
2. Agent captures identity, contact, preferences, and consent.
3. Agent checks availability across calendars/resources.
4. Agent ranks eligible appointment slots.
5. Agent books the appointment.
6. Agent sends SMS/email/calendar confirmation.
7. Agent sends reminders.
8. Agent conducts or supports the appointment.
9. Agent records attendance and outcome.
10. Agent sends summary and next steps.
11. Agent attempts to book the next appointment.
12. Agent calculates appointment performance score.
13. Agent aggregates weekly KPI trends.
14. Agent identifies performance gaps.
15. Agent proposes new skill candidates.
16. Agent scores candidates using weighted adoption model.
17. Agent approves only candidates that pass the 80% threshold, risk ceiling, and alignment floor.
18. Approved skills move to implementation.
19. Deferred skills remain queued until conditions change.
```

---

# 20. Implementation Summary

The Voice Agent Appointment Skill should be treated as a full business workflow, not just a calendar booking feature.

The agent must optimize for:

```text
Booked → Attended → Completed → Followed Up → Rebooked
```

The strongest sign of success is not the first appointment.

The strongest sign of success is a completed appointment that leads to an attended second appointment.
