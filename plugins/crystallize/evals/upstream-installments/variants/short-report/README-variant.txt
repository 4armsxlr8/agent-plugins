第 5 段階で測った「問いだけ」の版。v0.16.0 (コミット 1fc02b9) の spec・html-report に重ねる差し替えで、測った中身の記録として残す。
v0.17.0 でこの形を本体に取り込んだ (問わずに決めたことの節・字数の上限・選択肢の記号・「前提が違う」の入力欄を足した)。
v0.17.0 以降の plugin に重ねると、question-evaluator など差し替えていないスキルと書式が食い違うので、重ねない。
測り直すときは skills/ だけを v0.16.0 から取り出し (`git checkout 1fc02b9 -- plugins/crystallize/skills`)、今の evals/ から `--variant short-report` で走らせる。終わったら `git checkout HEAD -- plugins/crystallize/skills` で戻す。今の本体は `--variant base` で読み込む。
