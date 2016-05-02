import random
import sys
from inspect import isclass

def genGrow(pset, min_, max_, type_=None):
    """Generate an expression where each leaf might have a different depth
    between *min* and *max*.
    :param pset: Primitive set from which primitives are selected.
    :param min_: Minimum height of the produced trees.
    :param max_: Maximum Height of the produced trees.
    :param type_: The type that should return the tree when called, when
                  :obj:`None` (default) the type of :pset: (pset.ret)
                  is assumed.
    :returns: A grown tree with leaves at possibly different depths.
    """
    def condition(height, depth):
        """Expression generation stops when the depth is equal to height
        or when it is randomly determined that a a node should be a terminal.
        """
        return depth == height or \
            (depth >= min_ and random.random() < pset.terminalRatio)
    return generate(pset, min_, max_, condition, type_)

def generate(pset, min_, max_, condition, type_=None):
    """Generate a Tree as a list of list. The tree is build
    from the root to the leaves, and it stop growing when the
    condition is fulfilled.
    :param pset: Primitive set from which primitives are selected.
    :param min_: Minimum height of the produced trees.
    :param max_: Maximum Height of the produced trees.
    :param condition: The condition is a function that takes two arguments,
                      the height of the tree to build and the current
                      depth in the tree.
    :param type_: The type that should return the tree when called, when
                  :obj:`None` (default) the type of :pset: (pset.ret)
                  is assumed.
    :returns: A grown tree with leaves at possibly different depths
              dependending on the condition function.
    """
    expr = []
    height = random.randint(min_, max_)
    stack = [(0, type_)]
    while len(stack) != 0:
        depth, type_ = stack.pop()
        # At the bottom of the tree
        if condition(height, depth):
            # Try finding a terminal
            try:
                term = random.choice(pset.terminals[type_])
                
                if isclass(term):
                    term = term()
                expr.append(term)                
            # No terminal fits
            except:
                # So pull the depth back one layer, and start looking for primitives
                try:
                    depth -= 1
                    prim = random.choice(pset.primitives[type_])
          
                    expr.append(prim)
                    for arg in reversed(prim.args):
                        stack.append((depth+1, arg)) 
                                    
                # No primitive fits, either - that's an error
                except IndexError:
                    _, _, traceback = sys.exc_info()
                    raise IndexError("The gp.generate function tried to add "\
                                      "a primitive of type '%s', but there is "\
                                      "none available." % (type_,), traceback)

        # Not at the bottom of the tree
        else:
            # Check for primitives
            try:
                prim = random.choice(pset.primitives[type_])
          
                expr.append(prim)
                for arg in reversed(prim.args):
                    stack.append((depth+1, arg))                 
            # No primitive fits
            except:                
                # So check for terminals
                try:
                    term = random.choice(pset.terminals[type_])
                
                # No terminal fits, either - that's an error
                except IndexError:
                    _, _, traceback = sys.exc_info()
                    raise IndexError("The gp.generate function tried to add "\
                                      "a terminal of type '%s', but there is "\
                                      "none available." % (type_,), traceback)
                if isclass(term):
                    term = term()
                expr.append(term)

    return expr