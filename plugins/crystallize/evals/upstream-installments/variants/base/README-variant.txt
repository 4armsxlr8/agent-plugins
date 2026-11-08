差し替えなし。今の plugin を短い版と同じ写しの仕組みで読み込むための空の版。
v0.17.0 から今の plugin のラウンドレポートは問いだけの短い形なので、第 5 段階の「今の版」(長い形) を測り直すには skills/ だけを v0.16.0 から取り出し (`git checkout 1fc02b9 -- plugins/crystallize/skills`)、今の evals/ で走らせる。終わったら `git checkout HEAD -- plugins/crystallize/skills` で戻す。
