<!-- pr-preamble:start -->
> **Source:** Issue #481

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
### Issue Deduplication
- [ ] Create embedding generation for issue descriptions using OpenAI/GitHub Models
- [ ] Build FAISS vector store from existing open issues
- [ ] Implement similarity search with configurable threshold
- [ ] Post advisory comment linking similar issues
### Label Matching
- [ ] Build vector store from repo labels (cache since labels rarely change)
- [ ] Replace `findMatchingLabel()` Levenshtein logic with semantic search
- [ ] Add fallback to Levenshtein for edge cases (very short labels)
### Shared Infrastructure
- [ ] Create `scripts/langchain/semantic_matcher.py` for shared embeddings logic
- [ ] Add tests for both issue and label semantic similarity
- [ ] Deprecate/remove Levenshtein-based matching where applicable

#### Acceptance criteria
- [ ] New issues compared against existing open issues using embeddings
- [ ] High semantic similarity triggers warning comment for issues
- [ ] Label matching catches synonyms (defect→bug, improvement→enhancement)
- [ ] Related issues linked for context
- [ ] Does not block issue creation (advisory only)
- [ ] Catches "same idea, different phrasing" that Levenshtein misses

<!-- auto-status-summary:end -->
