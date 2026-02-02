#!/bin/bash
for f in .github/workflows/*.yml; do
  awk '
    /^[[:space:]]+token: \$\{\{ steps\.app_token/ {
      if (prev_line ~ /^[[:space:]]+token: \$\{\{ steps\.app_token/) {
        print FILENAME ":" NR-1 " and " NR
        exit
      }
      prev_line = $0
    }
    { if (!/^[[:space:]]+token:/) prev_line="" }
  ' "$f"
done | sort -u
