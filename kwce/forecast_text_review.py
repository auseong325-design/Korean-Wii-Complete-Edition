"""Native text-style review cases; failures are simulated, never NAND damage."""
CASES=([('error0',f'textTUS{i}')for i in range(8)]+
       [('error1','textTUS')]+[('error2',f'textTUS{i}')for i in range(3)]+
       [('error3','textTUS')]+[('error4',f'textTUS{i}')for i in range(2)]+
       [('life_no_service',f'textTUS{i}')for i in range(7)])
