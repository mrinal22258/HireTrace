LLM endpoint healthy=True 1/1 endpoints online (http://127.0.0.1:11434: OK)

run 1: 24.68s
run 2: 26.25s
run 3: 31.41s

step                                               median      min      max  % of total
---------------------------------------------------------------------------------------
CrossSourceVerificationAgent                       19.427   14.617   23.710       74.0%
ClaimCriticAgent                                    6.758    5.486    7.658       25.7%
retrieval_index_built                               0.053    0.041    4.571        0.2%
RubricScorer (Deterministic Baseline A)             0.000    0.000    0.000        0.0%
RequirementMappingAgent                             0.000    0.000    0.000        0.0%
EvidenceAggregationAgent                            0.000    0.000    0.001        0.0%
RecommendationWriterAgent                           0.000    0.000    0.001        0.0%
---------------------------------------------------------------------------------------
TOTAL                                              26.253

First run vs. later runs (cold model load shows up here):
 run 1: 24.68s later median: 28.83s
