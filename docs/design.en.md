# Design Document

[日本語版はこちら](design.md)

## What problem does this app solve?

### Who uses it, and when

This app is for companies that want to understand defect trends and decide how to address them. It is meant for situations like these:

- Seeing which problems occur and what percentage of all complaints each one accounts for, to decide whether it needs to be addressed
- Reading customers' own words to find out what the real problem is and what should be fixed in the next model

### The problem I faced

- When filing a defect report, I wanted to check whether the same defect had already been reported. However, the search could not find reports by meaning (semantic search), so the same defect was often filed more than once.
- If we could know in advance which problems to focus on, we could concentrate our testing on those areas.

### Why I built this app

I set myself the challenge of building a tool that uses raw in-vehicle defect data to analyze problems and support planning for the next model. I also wanted to understand the whole process of building an application from start to finish.

### The data used here vs. data in real work

- I have experience in IVI (in-vehicle infotainment) testing. Since there is no public dataset focused on IVI, I built this sample app using publicly available customer complaint data for vehicles in general.
- In real work, the data may be customer complaints, or raw defect data recorded by testers within the customer's organization or by the development team. That kind of data is more accurate.

## Why I reclassified the complaints

If the raw data is used as is, it is unclear whether a complaint describes only what the customer saw, or where the real defect lies. So the complaints first needed to be sorted from the viewpoint of someone working on the product.

The classification rules are described in [`classification_spec.md`](classification_spec.md) (in Japanese).

## How to use the analysis page

The analysis page provides five basic charts, A to E. After reviewing the overview each chart gives, you can click on a chart to see the list of defects that match that condition.
