# **Moderator Agent Skill Specification**

## **Overview**

The Moderator Agent facilitates conflict resolution between two participants. It gathers perspectives, guides discussions, and helps reveal shared truths.

## **Flow**

1. The agent begins a call with two participants.  
2. Each gives an opening statement.  
3. The agent predicts tendencies based on profiles and data.  
4. It dynamically adjusts the conversation flow to guide toward resolution.  
5. It tracks satisfaction, progress, and its own performance.  
6. The agent logs outcomes and learns from each session.

## **Data Objects**

* Participant Profile: name, prior interactions, key triggers.  
* Emotional State: sentiment score, mood indicators.  
* Perceived Truth: participant’s initial belief vs. post-call shift.  
* Session Log: timeline of statements, key moments, outcomes.

## **KPIs**

1. Participant Satisfaction: real-time sentiment analysis, post-call rating.  
2. Agent Performance: accuracy, efficiency, learning iteration count.  
3. Participant Progress: shift in openness to broader truth.  
4. Interaction Timing: efficiency of resolution steps.

## **Mathematical Models (Examples)**

* Satisfaction Index: sentiment score (0-1) averaged over time.  
* Performance: accuracy \= correct guidance steps / total steps.  
* Progress: belief shift \= (post-call openness \- pre-call openness).

