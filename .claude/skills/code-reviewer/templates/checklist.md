# Code Review Checklist

Quick reference checklist for code reviews. Use during the review process.

---

## Plan Alignment

- [ ] All planned features implemented
- [ ] No significant scope creep
- [ ] Deviations documented and justified
- [ ] Requirements fully met

---

## Code Quality

### Correctness
- [ ] Logic is correct and handles edge cases
- [ ] Error handling is comprehensive
- [ ] Input validation present
- [ ] Return values checked

### Readability
- [ ] Clear, descriptive naming
- [ ] Functions are focused (single responsibility)
- [ ] Comments explain "why", not "what"
- [ ] Consistent formatting

### Maintainability
- [ ] DRY - no code duplication
- [ ] YAGNI - no over-engineering
- [ ] Easy to modify and extend
- [ ] Dependencies are minimal

---

## Architecture

### SOLID Principles
- [ ] **S** - Single Responsibility
- [ ] **O** - Open/Closed
- [ ] **L** - Liskov Substitution
- [ ] **I** - Interface Segregation
- [ ] **D** - Dependency Inversion

### Design
- [ ] Proper separation of concerns
- [ ] Loose coupling between modules
- [ ] Consistent with existing patterns
- [ ] Scalable design

---

## Testing

- [ ] Tests exist for new functionality
- [ ] Tests are meaningful (not just coverage)
- [ ] Edge cases tested
- [ ] Error cases tested
- [ ] Tests are readable and maintainable

---

## Security

- [ ] No hardcoded secrets
- [ ] Input properly sanitized
- [ ] SQL injection prevented
- [ ] XSS prevented
- [ ] Authentication/Authorization correct
- [ ] Sensitive data protected

---

## Performance

- [ ] No N+1 queries
- [ ] Appropriate caching considered
- [ ] No memory leaks
- [ ] Async operations used appropriately
- [ ] Resource cleanup handled

---

## Documentation

- [ ] Public APIs documented
- [ ] Complex logic explained
- [ ] README updated if needed
- [ ] Breaking changes noted

---

## Red Flags (Stop Review)

If any of these are present, mark as **🔴 Critical**:

- Hardcoded credentials
- SQL with string concatenation
- Disabled/skipped tests
- TODO for critical functionality
- Catch-all without logging
- Production code with no tests
