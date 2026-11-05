(function (global) {
  var DEFAULT_STEPS = [
    {
      step_id: 'verify',
      number: '01',
      title: 'Verify domain',
      description: 'Add DNS TXT or HTTPS file ownership. This ties every run and report to the client.',
      action: 'Verify domain',
      proof: 'DNS or HTTPS ownership proof',
      plan: 'free',
    },
    {
      step_id: 'pages',
      number: '02',
      title: 'Run page audit',
      description: 'Audit sitemap URLs for title, meta, schema, crawler access, content, and score issues.',
      action: 'Run page audit',
      proof: 'Before baseline by URL',
      plan: 'free',
    },
    {
      step_id: 'benchmark',
      number: '03',
      title: 'Run benchmark',
      description: 'Test target prompts against competitors and record where AI answers cite or miss the client.',
      action: 'Run benchmark',
      proof: 'Before baseline by prompt',
      plan: 'free',
    },
    {
      step_id: 'skill',
      number: '04',
      title: 'Copy Skill Files',
      description: 'Give Cursor, Claude, Codex, or the CLI the GEOSITION workflow and file context before fixing.',
      action: 'Copy Skill Files',
      proof: 'Fix handoff context',
      plan: 'free',
    },
    {
      step_id: 'fix',
      number: '05',
      title: 'Fix pages',
      description: 'Apply the highest-impact recommendations to the URLs and prompts with visible gaps.',
      action: 'Fix client pages',
      proof: 'Implementation notes',
      plan: 'free',
    },
    {
      step_id: 'report',
      number: '06',
      title: 'Re-run proof',
      description: 'Re-run audits, benchmarks, and weekly evidence so clients see before/after movement.',
      action: 'Weekly proof',
      proof: 'Before/after deltas',
      plan: 'paid',
    },
  ];

  function cloneStep(step) {
    var copy = {};
    Object.keys(step || {}).forEach(function (key) {
      copy[key] = step[key];
    });
    return copy;
  }

  function deriveAgencyLoop(input) {
    var state = input || {};
    var current = state.current_step || (state.locked ? 'verify' : 'pages');
    var currentSeen = false;
    var steps = (state.steps && state.steps.length ? state.steps : DEFAULT_STEPS).map(function (rawStep) {
      var step = cloneStep(rawStep);
      var stepId = step.step_id || step.step || '';
      if (!currentSeen && stepId !== current) {
        step.state = 'done';
        step.label = 'Done';
      } else if (stepId === current) {
        step.state = 'current';
        step.label = step.label || 'Now';
        currentSeen = true;
      } else {
        step.state = step.state || 'waiting';
        step.label = step.label || 'Waiting';
      }
      step.step_id = stepId;
      return step;
    });
    return {
      current_step: current,
      next_action: state.next_action || 'Verify domain',
      next_action_target: state.next_action_target || current,
      summary: state.summary || 'Verify ownership before audits and benchmarks unlock.',
      proof_focus: state.proof_focus || 'No client proof yet.',
      paid_boundary:
        state.paid_boundary ||
        'Paid access automates recurring audits, benchmarks, CLI runs, and weekly proof reports.',
      steps: steps,
    };
  }

  function skillCopyTransitions(locked, blocked) {
    if (locked) {
      return [
        { step: 'skill', state: 'done', label: blocked ? 'Selected' : 'Copied' },
        { step: 'verify', state: 'current', label: 'Verify next' },
      ];
    }
    return [
      { step: 'skill', state: blocked ? 'current' : 'done', label: blocked ? 'Select bundle' : 'Copied' },
      { step: 'fix', state: 'current', label: 'Fix next' },
    ];
  }

  global.GEOSITION_DASHBOARD_LOOP = {
    deriveAgencyLoop: deriveAgencyLoop,
    skillCopyTransitions: skillCopyTransitions,
  };
})(window);
